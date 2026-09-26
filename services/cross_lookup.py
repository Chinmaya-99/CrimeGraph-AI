"""
cross_lookup_service.py
========================
Step 3 — Cross-DB Lookup Service
AI-Powered Criminal Network Analysis System

Flow:
    NER output (list of entities)
        → fan out across 6 PostgreSQL tables
    → group all hits per entity
    → compute entity score (Step 4 inline)
    → save results back to extracted_entities
    → log every match to audit_ledger
    → return structured CrossLookupResult

Caller owns the transaction (flush only — no commit here).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from services.new_ner import _load_gazetteer
from services.new_ner import (
    get_entity_text,
    get_entity_type,
    normalize_phone_digits,
    normalize_vehicle_plate,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Scoring weights (must sum to 1.0)
# ─────────────────────────────────────────────
SCORE_WEIGHTS = {
    "contact":      0.18,
    "bank":         0.22,
    "crime":        0.25,
    "surveillance": 0.13,
    "social":       0.09,
    "fir":          0.13,
}

# How many DB hits count as "saturated" (score = 1.0 for that dimension)
SATURATION = {
    "contact":      10,
    "bank":          5,
    "crime":         3,
    "surveillance":  5,
    "social":        8,
    "fir":           3,
}

# ─────────────────────────────────────────────
# Entity pre-filter — skip garbage before DB
# ─────────────────────────────────────────────




# Types with no DB lookup value — skip entirely
_SKIP_TYPES = {"MONEY", "FIR_NUMBER", "CASE_ID","type","label"}

# Types we actually query against
_LOOKUPABLE_TYPES = {"PERSON", "PHONE", "VEHICLE", "ORGANIZATION", "ACCOUNT", "LOCATION"}

_BAD_PERSON_SUFFIXES = {
    "police", "station", "inspector", "officer",
    "constable", "department", "india", "court"
}
_FIELD_KEYWORDS = {
    "incident location", "preliminary investigation",
    "at approximately", "the vehicle", "the location",
    "organization eastern", "police station",
}

def _is_garbage_entity(entity: dict) -> bool:
    label = get_entity_type(entity)
    value = get_entity_text(entity).strip()
    source = entity.get("source", "")

    # Skip non-lookupable types entirely
    if label in _SKIP_TYPES:
        return True

    if label not in _LOOKUPABLE_TYPES:
        return True

    # Empty or too short
    if len(value) <= 3:
        return True

    # Starts with lowercase "the " — always garbage
    if value.lower().startswith("the "):
        return True

    # Sentence fragment — contains period or newline and is long
    if "\n" in value or (". " in value and len(value) > 30):
        return True

    # Ends with "approximately", "investigation" etc — fragment bleed
    _BAD_ENDINGS = (
        "approximately", "investigation", "preliminary",
        "location", "during", "vehicle"
    )
    if any(value.lower().rstrip(".").endswith(e) for e in _BAD_ENDINGS):
        return True

    # Field keyword contamination
    if any(kw in value.lower() for kw in _FIELD_KEYWORDS):
        return True

    # PERSON with 4+ words — merged span
    if label == "PERSON":
        last_word = value.split()[-1].lower().rstrip(".")
        if last_word in _BAD_PERSON_SUFFIXES:
            return True
        # 3+ word spaCy persons are usually merged spans
        if source == "spacy" and len(value.split()) >= 3:
            return True

    return False

def get_lookup_value(entity: dict) -> str:
    """
    Return the canonical value used for database lookup.

    The NER layer may provide `normalized_value`. When it does,
    cross-lookup uses that value instead of the raw display text.

    Examples
    --------
        PHONE
            "+91 98765 43210"
                ↓
            "9876543210"

        VEHICLE
            "OD-05-AB-1234"
                ↓
            "OD05AB1234"

    Backward compatibility
    -----------------------
    Older NER output may not contain `normalized_value`, so the
    original entity text is used as a fallback.
    """

    normalized = (
        entity.get("normalized_value")
        or ""
    ).strip()

    if normalized:
        return normalized

    return get_entity_text(entity)

SYSTEM_ACTOR_ID = None  # no fake user row; column is nullable


# ─────────────────────────────────────────────
# Data containers
# ─────────────────────────────────────────────

@dataclass
class EntityHits:
    """All DB hits for a single extracted entity."""
    entity_type:   str
    entity_value:  str
    fir_id:        int

    contact_hits:     list[dict] = field(default_factory=list)
    bank_hits:        list[dict] = field(default_factory=list)
    crime_hits:       list[dict] = field(default_factory=list)
    surveillance_hits:list[dict] = field(default_factory=list)
    social_hits:      list[dict] = field(default_factory=list)
    fir_hits:         list[dict] = field(default_factory=list)

    entity_score: float = 0.0
    db_hit_count: int   = 0  # number of tables that returned at least one row

    def all_hits(self) -> dict[str, list[dict]]:
        return {
            "contact":      self.contact_hits,
            "bank":         self.bank_hits,
            "crime":        self.crime_hits,
            "surveillance": self.surveillance_hits,
            "social":       self.social_hits,
            "fir":          self.fir_hits,
        }


@dataclass
class CrossLookupResult:
    """Final result returned to the caller (Step 5 — Groq)."""
    fir_id:        int
    total_entities: int
    entity_hits:   list[EntityHits]
    processed_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────
# Scoring
# ─────────────────────────────────────────────

def _tables_hit_count(hits: EntityHits) -> int:
    """Count of source tables that returned at least one row (schema meaning)."""
    return sum(1 for rows in hits.all_hits().values() if rows)

def _compute_score(hits: EntityHits) -> float:
    """
    Weighted, saturation-capped identity score.

    Location matches are intentionally excluded from the score because
    a common location (for example, Odisha or Cuttack) is contextual
    evidence, not strong evidence that the extracted entity itself
    is the same person/organization/vehicle.

    Location hits are still preserved in the returned hit data so they
    can be used later by the LLM/network-analysis layer.

    Each scored dimension:
        min(hit_count / saturation, 1.0) × weight

    Final score is clamped to [0.0, 1.0].
    """

    # Location matches are contextual evidence only.
    # They must never contribute to identity confidence.
    if hits.entity_type == "LOCATION":
        return 0.0

    # Identity-bearing evidence only.
    dims = {
        "contact":      len(hits.contact_hits),
        "bank":         len(hits.bank_hits),
        "crime":        len(hits.crime_hits),
        "surveillance": len(hits.surveillance_hits),
        "social":       len(hits.social_hits),
        "fir":          len(hits.fir_hits),
    }

    score = sum(
        min(count / SATURATION[dim], 1.0) * SCORE_WEIGHTS[dim]
        for dim, count in dims.items()
    )

    return round(min(max(score, 0.0), 1.0), 4)


# ─────────────────────────────────────────────
# Per-table lookup helpers
# Each returns list[dict] — raw rows as dicts
# ─────────────────────────────────────────────

def _rows_to_dicts(result) -> list[dict]:
    """Convert SQLAlchemy CursorResult rows to plain dicts."""
    keys = list(result.keys())
    return [dict(zip(keys, row)) for row in result.fetchall()]


def _word_pattern(value: str) -> str:
    """POSIX word-boundary pattern (not substring ILIKE)."""
    escaped = re.sub(r"([.\\+*?[^\]$(){}=!<>|:-])", r"\\\1", value)
    return rf"\y{escaped}\y"


def _lookup_contact(db: Session, entity: dict) -> list[dict]:
    """
    Search contact_records using strict identity matching.

    PERSON  → exact normalized caller/receiver name
    PHONE   → exact normalized 10-digit caller/receiver phone
    LOCATION→ contextual location match
    """

    etype = get_entity_type(entity)
    value = get_lookup_value(entity).strip()

    if not value:
        return []

    # ------------------------------------------------------------
    # PERSON
    # ------------------------------------------------------------
    if etype == "PERSON":
        sql = text("""
            SELECT contact_id,
                   caller_name,
                   caller_phone,
                   receiver_name,
                   receiver_phone,
                   call_timestamp,
                   duration_seconds,
                   call_type
            FROM contact_records
            WHERE LOWER(TRIM(caller_name)) = LOWER(TRIM(:v))
               OR LOWER(TRIM(receiver_name)) = LOWER(TRIM(:v))
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {"v": value},
            )
        )

    # ------------------------------------------------------------
    # PHONE
    # ------------------------------------------------------------
    if etype == "PHONE":
        digits = normalize_phone_digits(value)

        if not digits:
            return []

        sql = text("""
            SELECT contact_id,
                   caller_name,
                   caller_phone,
                   receiver_name,
                   receiver_phone,
                   call_timestamp,
                   duration_seconds,
                   call_type
            FROM contact_records
            WHERE RIGHT(
                      regexp_replace(caller_phone, '[^0-9]', '', 'g'),
                      10
                  ) = :v
               OR RIGHT(
                      regexp_replace(receiver_phone, '[^0-9]', '', 'g'),
                      10
                  ) = :v
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {"v": digits},
            )
        )

    # ------------------------------------------------------------
    # LOCATION
    # ------------------------------------------------------------
    if etype == "LOCATION":
        sql = text("""
            SELECT contact_id,
                   caller_name,
                   caller_phone,
                   caller_location,
                   receiver_name,
                   receiver_phone,
                   receiver_location,
                   call_timestamp
            FROM contact_records
            WHERE caller_location   ~* :pat
               OR receiver_location ~* :pat
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {"pat": _word_pattern(value)},
            )
        )

    return []

def _lookup_bank(db: Session, entity: dict) -> list[dict]:
    """
    Search bank_records using strict identity matching.

    PERSON   → exact normalized sender/receiver name
    ACCOUNT  → exact normalized account number
    LOCATION → contextual location match
    """

    etype = get_entity_type(entity)
    value = get_lookup_value(entity).strip()

    if not value:
        return []

    # ------------------------------------------------------------
    # PERSON
    # ------------------------------------------------------------
    if etype == "PERSON":
        sql = text("""
            SELECT bank_record_id,
                   sender_account_holder_name,
                   sender_account_number,
                   sender_location,
                   receiver_account_holder_name,
                   receiver_account_number,
                   receiver_location,
                   transaction_amount,
                   transaction_date
            FROM bank_records
            WHERE LOWER(TRIM(sender_account_holder_name))
                      = LOWER(TRIM(:v))
               OR LOWER(TRIM(receiver_account_holder_name))
                      = LOWER(TRIM(:v))
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {"v": value},
            )
        )

    # ------------------------------------------------------------
    # ACCOUNT
    # ------------------------------------------------------------
    if etype == "ACCOUNT":
        account = re.sub(r"[^0-9A-Za-z]", "", value)

        if not account:
            return []

        sql = text("""
            SELECT bank_record_id,
                   sender_account_holder_name,
                   sender_account_number,
                   sender_location,
                   receiver_account_holder_name,
                   receiver_account_number,
                   receiver_location,
                   transaction_amount,
                   transaction_date
            FROM bank_records
            WHERE regexp_replace(
                      COALESCE(sender_account_number, ''),
                      '[^0-9A-Za-z]',
                      '',
                      'g'
                  ) = :v
               OR regexp_replace(
                      COALESCE(receiver_account_number, ''),
                      '[^0-9A-Za-z]',
                      '',
                      'g'
                  ) = :v
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {"v": account},
            )
        )

    # ------------------------------------------------------------
    # LOCATION
    # ------------------------------------------------------------
    if etype == "LOCATION":
        sql = text("""
            SELECT bank_record_id,
                   sender_account_holder_name,
                   sender_location,
                   receiver_account_holder_name,
                   receiver_location,
                   transaction_amount,
                   transaction_date
            FROM bank_records
            WHERE sender_location   ~* :pat
               OR receiver_location ~* :pat
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {"pat": _word_pattern(value)},
            )
        )

    return []

def _lookup_crime(db: Session, entity: dict) -> list[dict]:
    """
    Search previous_crime_records using strict identity matching.

    PERSON   → exact normalized person name
    LOCATION → contextual location match
    """

    etype = get_entity_type(entity)
    value = get_lookup_value(entity).strip()

    if not value:
        return []

    if etype == "PERSON":
        sql = text("""
            SELECT history_id,
                   person_name,
                   offense,
                   offense_category,
                   case_status,
                   district,
                   state,
                   police_station
            FROM previous_crime_records
            WHERE LOWER(TRIM(person_name))
                      = LOWER(TRIM(:v))
        """)

        return _rows_to_dicts(
            db.execute(sql, {"v": value})
        )

    if etype == "LOCATION":
        sql = text("""
            SELECT history_id,
                   person_name,
                   offense,
                   offense_category,
                   case_status,
                   district,
                   state,
                   police_station
            FROM previous_crime_records
            WHERE district       ~* :pat
               OR state          ~* :pat
               OR police_station ~* :pat
        """)

        return _rows_to_dicts(
            db.execute(sql, {"pat": _word_pattern(value)})
        )

    return []
def _lookup_surveillance(
    db: Session,
    entity: dict,
) -> list[dict]:
    """
    Strict surveillance lookup.

    PERSON  → exact entity_name when entity_type represents a person
    PHONE   → exact entity_name when stored as a phone entity
    VEHICLE → exact entity_name when stored as a vehicle entity
    LOCATION → contextual location match

    Uses the actual surveillance_records schema.
    """

    etype = get_entity_type(entity)
    value = get_lookup_value(entity).strip()

    if not value:
        return []

    # ------------------------------------------------------------
    # PERSON / PHONE / VEHICLE
    # ------------------------------------------------------------
    if etype in {"PERSON", "PHONE", "VEHICLE"}:
        sql = text("""
            SELECT
                surveillance_id,
                entity_name,
                entity_type,
                camera_id,
                source_type,
                source_reference,
                location,
                location_name,
                observed_at,
                event_description
            FROM surveillance_records
            WHERE
                LOWER(TRIM(entity_name))
                    = LOWER(TRIM(:value))
                AND LOWER(TRIM(entity_type))
                    = LOWER(TRIM(:entity_type))
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {
                    "value": value,
                    "entity_type": etype,
                },
            )
        )

    # ------------------------------------------------------------
    # LOCATION
    # ------------------------------------------------------------
    if etype == "LOCATION":
        sql = text("""
            SELECT
                surveillance_id,
                entity_name,
                entity_type,
                camera_id,
                source_type,
                source_reference,
                location,
                location_name,
                observed_at,
                event_description
            FROM surveillance_records
            WHERE
                location_name ~* :pattern
                OR location ~* :pattern
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {
                    "pattern": _word_pattern(value),
                },
            )
        )

    return []
def _lookup_social(
    db: Session,
    entity: dict,
) -> list[dict]:
    """
    Strict social-media lookup.

    PERSON:
        Exact match against username or mentioned_users.

    PHONE:
        Exact normalized match against phone_numbers.

    Uses the actual social_media_records schema.
    """

    etype = get_entity_type(entity)
    value = get_lookup_value(entity).strip()

    if not value:
        return []

    # ------------------------------------------------------------
    # PERSON LOOKUP
    # ------------------------------------------------------------
    if etype == "PERSON":
        sql = text("""
            SELECT
                social_media_record_id,
                platform,
                user_id,
                username,
                post_id,
                post_content,
                post_timestamp,
                mentioned_users,
                phone_numbers,
                hashtags,
                external_links
            FROM social_media_records
            WHERE
                LOWER(TRIM(username))
                    = LOWER(TRIM(:value))
                OR EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(
                        COALESCE(mentioned_users, '[]'::jsonb)
                    ) AS mentioned_user
                    WHERE LOWER(TRIM(mentioned_user))
                        = LOWER(TRIM(:value))
                )
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {
                    "value": value,
                },
            )
        )

    # ------------------------------------------------------------
    # PHONE LOOKUP
    # ------------------------------------------------------------
    if etype == "PHONE":
        phone = normalize_phone_digits(value)

        if not phone:
            return []

        sql = text("""
            SELECT
                social_media_record_id,
                platform,
                user_id,
                username,
                post_id,
                post_content,
                post_timestamp,
                mentioned_users,
                phone_numbers,
                hashtags,
                external_links
            FROM social_media_records
            WHERE EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(
                    COALESCE(phone_numbers, '[]'::jsonb)
                ) AS phone_number
                WHERE
                    RIGHT(
                        regexp_replace(phone_number, '[^0-9]', '', 'g'),
                        10
                    )
                    =
                    RIGHT(:phone, 10)
            )
        """)

        return _rows_to_dicts(
            db.execute(
                sql,
                {
                    "phone": phone,
                },
            )
        )

    return []
def _lookup_fir(
    db: Session,
    entity: dict,
    current_fir_id: int | None = None,
) -> list[dict]:
    """
    Search fir_records using strict identity matching.

    PERSON       → exact person name inside JSONB array
    ORGANIZATION → exact organization name inside JSONB array
    VEHICLE      → exact normalized vehicle number inside JSONB array
    PHONE        → exact normalized phone number inside JSONB array
    LOCATION     → contextual location match

    The current FIR is excluded.

    Additionally, FIRs belonging to the same case_id or the same
    fir_number are excluded so the lookup only represents
    genuinely separate FIR records.
    """

    etype = get_entity_type(entity)
    value = get_lookup_value(entity).strip()

    if not value:
        return []

    # ------------------------------------------------------------
    # Find the current FIR's case identity.
    #
    # We use this in addition to fir_id because duplicate/imported
    # records can represent the same case under different IDs.
    # ------------------------------------------------------------
    exclusion = ""
    params: dict[str, Any] = {"v": value}

    if current_fir_id is not None:
        current = db.execute(
            text("""
                SELECT case_id, fir_number
                FROM fir_records
                WHERE fir_id = :current_fir_id
            """),
            {"current_fir_id": current_fir_id},
        ).mappings().first()

        if current:
            exclusion = """
                AND fir_id != :current_fir_id
                AND (
                    case_id IS DISTINCT FROM :current_case_id
                )
                AND (
                    fir_number IS NULL
                    OR :current_fir_number IS NULL
                    OR fir_number IS DISTINCT FROM :current_fir_number
                )
            """

            params["current_fir_id"] = current_fir_id
            params["current_case_id"] = current["case_id"]
            params["current_fir_number"] = current["fir_number"]

    # ------------------------------------------------------------
    # PERSON
    # ------------------------------------------------------------
    if etype == "PERSON":
        sql = text(f"""
            SELECT fir_id,
                   case_id,
                   fir_number,
                   police_station,
                   district,
                   state,
                   incident_date,
                   status
            FROM fir_records
            WHERE EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(
                    COALESCE(persons_mentioned, '[]'::jsonb)
                ) AS person
                WHERE LOWER(TRIM(person))
                      = LOWER(TRIM(:v))
            )
            {exclusion}
        """)

        return _rows_to_dicts(
            db.execute(sql, params)
        )

    # ------------------------------------------------------------
    # ORGANIZATION
    # ------------------------------------------------------------
    if etype == "ORGANIZATION":
        sql = text(f"""
            SELECT fir_id,
                   case_id,
                   fir_number,
                   police_station,
                   district,
                   state,
                   incident_date,
                   status
            FROM fir_records
            WHERE EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(
                    COALESCE(organizations_mentioned, '[]'::jsonb)
                ) AS organization
                WHERE LOWER(TRIM(organization))
                      = LOWER(TRIM(:v))
            )
            {exclusion}
        """)

        return _rows_to_dicts(
            db.execute(sql, params)
        )

    # ------------------------------------------------------------
    # VEHICLE
    # ------------------------------------------------------------
    if etype == "VEHICLE":
        vehicle = normalize_vehicle_plate(value)

        if not vehicle:
            return []

        params["v"] = vehicle

        sql = text(f"""
            SELECT fir_id,
                   case_id,
                   fir_number,
                   police_station,
                   district,
                   state,
                   incident_date,
                   status
            FROM fir_records
            WHERE EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(
                    COALESCE(vehicles_mentioned, '[]'::jsonb)
                ) AS vehicle
                WHERE regexp_replace(
                          UPPER(vehicle),
                          '[^A-Z0-9]',
                          '',
                          'g'
                      ) = :v
            )
            {exclusion}
        """)

        return _rows_to_dicts(
            db.execute(sql, params)
        )

    # ------------------------------------------------------------
    # PHONE
    # ------------------------------------------------------------
    if etype == "PHONE":
        digits = normalize_phone_digits(value)

        if not digits:
            return []

        # Compare using the last 10 digits so +91 / spaces /
        # hyphens do not affect identity matching.
        params["v"] = digits[-10:]

        sql = text(f"""
            SELECT fir_id,
                   case_id,
                   fir_number,
                   police_station,
                   district,
                   state,
                   incident_date,
                   status
            FROM fir_records
            WHERE EXISTS (
                SELECT 1
                FROM jsonb_array_elements_text(
                    COALESCE(phones_mentioned, '[]'::jsonb)
                ) AS phone
                WHERE RIGHT(
                    regexp_replace(phone, '[^0-9]', '', 'g'),
                    10
                ) = :v
            )
            {exclusion}
        """)

        return _rows_to_dicts(
            db.execute(sql, params)
        )

    # ------------------------------------------------------------
    # LOCATION
    # ------------------------------------------------------------
    if etype == "LOCATION":
        params["pat"] = _word_pattern(value)
        params.pop("v", None)

        sql = text(f"""
            SELECT fir_id,
                   case_id,
                   fir_number,
                   police_station,
                   district,
                   state,
                   incident_date,
                   status
            FROM fir_records
            WHERE (
                EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(
                        COALESCE(locations_mentioned, '[]'::jsonb)
                    ) AS location
                    WHERE location ~* :pat
                )
                OR incident_location ~* :pat
                OR district ~* :pat
                OR state ~* :pat
            )
            {exclusion}
        """)

        return _rows_to_dicts(
            db.execute(sql, params)
        )

    return []
# ─────────────────────────────────────────────
# Audit helper
# ─────────────────────────────────────────────

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _log_audit(
    db: Session,
    event_type: str,
    target_table: str,
    target_record_id: int | None,
    actor_id: int | None,
    actor_role: str,
    metadata: dict,
) -> None:
    """
    Append a tamper-evident entry to audit_ledger.
    Advisory-locks the chain so concurrent uploads cannot fork previous_hash.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext('audit_ledger_chain'))"))

    last = db.execute(
        text("""
            SELECT chain_hash FROM audit_ledger
            ORDER BY ledger_id DESC
            LIMIT 1
            FOR UPDATE
        """)
    ).fetchone()
    previous_hash = last[0] if last else "GENESIS"

    record_data = json.dumps(
        {
            "event_type": event_type,
            "target_table": target_table,
            "target_record_id": target_record_id,
            "metadata": metadata,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
        default=str,
    )
    record_hash = _sha256(record_data)
    chain_hash  = _sha256(record_hash + previous_hash)

    db.execute(
        text("""
            INSERT INTO audit_ledger
                (event_type, actor_id, actor_role,
                 target_table, target_record_id,
                 record_hash, previous_hash, chain_hash, metadata)
            VALUES
                (:evt, :aid, :arl,
                 :tbl, :trid,
                 :rh,  :ph,  :ch,  CAST(:meta AS jsonb))
        """),
        {
            "evt":  event_type,
            "aid":  actor_id,
            "arl":  actor_role,
            "tbl":  target_table,
            "trid": target_record_id,
            "rh":   record_hash,
            "ph":   previous_hash,
            "ch":   chain_hash,
            "meta": json.dumps(metadata, default=str),
        },
    )


def log_data_ingested(
    db: Session,
    fir_id: int,
    source_file: str | None,
    source_hash: str | None,
    actor_id: int | None = SYSTEM_ACTOR_ID,
    actor_role: str = "system",
) -> None:
    """Write DATA_INGESTED with the source PDF hash."""
    _log_audit(
        db,
        event_type="DATA_INGESTED",
        target_table="fir_records",
        target_record_id=fir_id,
        actor_id=actor_id,
        actor_role=actor_role,
        metadata={
            "source_file": source_file,
            "source_hash": source_hash,
            "fir_id": fir_id,
        },
    )


# ─────────────────────────────────────────────
# Save entity + hits back to extracted_entities
# ─────────────────────────────────────────────

def _upsert_entity(db: Session, hits: EntityHits) -> int:
    """
    Insert or update the extracted_entities row for this entity.
    Relies on UNIQUE (fir_id, entity_type, entity_value).
    Returns the entity_id.
    """
    table_hits = _tables_hit_count(hits)

    result = db.execute(
        text("""
            INSERT INTO extracted_entities
                (fir_id, entity_type, entity_value,
                 db_hit_count, entity_score,
                 extraction_source)
            VALUES
                (:fid, :etype, :evalue,
                 :hc,  :es,
                 'cross_lookup_service')
            ON CONFLICT (fir_id, entity_type, entity_value)
            DO UPDATE SET
                db_hit_count = EXCLUDED.db_hit_count,
                entity_score = EXCLUDED.entity_score
            RETURNING entity_id
        """),
        {
            "fid":    hits.fir_id,
            "etype":  hits.entity_type,
            "evalue": hits.entity_value,
            "hc":     table_hits,
            "es":     hits.entity_score,
        },
    )
    return result.fetchone()[0]


# ─────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────

def _deduplicate_locations(entities: list[dict]) -> list[dict]:
    """
    If a LOCATION value is a substring of another LOCATION value,
    keep only the shorter canonical one if it's gazetteer-sourced.
    Drop redundant sub-location fragments.
    """
    locations = [e for e in entities if get_entity_type(e) == "LOCATION"]
    others    = [e for e in entities if get_entity_type(e) != "LOCATION"]

    filtered_locs = []
    for loc in locations:
        val = get_entity_text(loc).lower()
        # Drop if it's a superset of a gazetteer location
        # e.g. "Cuttack Railway Station" contains "cuttack" → keep
        # but drop if confidence < 0.95 and no DB hits expected
        if loc.get("source") in ("gazetteer",):
            filtered_locs.append(loc)
            continue
        # Keep specific named places (Railway Station, Bus Stand etc.)
        # but drop if the value contains sentence words
        if any(bad in val for bad in ("approximately", "investigation", "the ", ". ")):
            continue
        filtered_locs.append(loc)

    return others + filtered_locs


def _deduplicate_entities(entities: list[dict]) -> list[dict]:
    """
    Remove duplicate entities before database lookup.

    Deduplication is based on:
        entity type + canonical lookup value

    The first occurrence is preserved so the original NER
    metadata remains available for display and audit.
    """

    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []

    for entity in entities:
        label = get_entity_type(entity)
        value = get_lookup_value(entity).strip()

        if not label or not value:
            continue

        key = (
            label.upper(),
            value.lower(),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(entity)

    return unique
def run_cross_lookup(
    db:       Session,
    fir_id:   int,
    entities: list[dict],
    actor_id: int | None = SYSTEM_ACTOR_ID,
    actor_role: str = "system",
) -> CrossLookupResult:
    """
    Fan out every extracted entity across all 6 source tables.

    Args:
        db:         SQLAlchemy session (caller manages commit/rollback)
        fir_id:     ID of the FIR being analysed
        entities:   Raw NER output list
        actor_id:   User ID for audit log (None = system, no fake actor)
        actor_role: Role string for audit log

    Returns:
        CrossLookupResult with all hits + scores per entity
    """
    logger.info("Cross-lookup started | fir_id=%s | entities=%d", fir_id, len(entities))

    all_entity_hits: list[EntityHits] = []
    entities = _deduplicate_entities(entities)

    for entity in entities:
        display_value = get_entity_text(entity)
        value = get_lookup_value(entity)
        label = get_entity_type(entity)

        #=====PRE_FILLTER=======
        if _is_garbage_entity(entity):
            logger.debug("Skipped garbage entity: [%s] %s", label, display_value)
            continue

        if not value:
            continue

        # Use the canonical value for every database lookup while
        # preserving the original NER entity for display/audit purposes.
        lookup_entity = {
            **entity,
            "text": value,
            "normalized_value": value,
        }

        hits = EntityHits(
            entity_type=label,
            entity_value=value,
            fir_id=fir_id,
        )

        hits.contact_hits      = _lookup_contact(db, lookup_entity)
        hits.bank_hits         = _lookup_bank(db, lookup_entity)
        hits.crime_hits        = _lookup_crime(db, lookup_entity)
        hits.surveillance_hits = _lookup_surveillance(db, lookup_entity)
        hits.social_hits       = _lookup_social(db, lookup_entity)
        hits.fir_hits = _lookup_fir(db, lookup_entity, fir_id)

        hits.entity_score = _compute_score(hits)
        hits.db_hit_count = _tables_hit_count(hits)

        entity_id = _upsert_entity(db, hits)

        _log_audit(
            db,
            event_type       = "ENTITY_EXTRACTED",
            target_table     = "extracted_entities",
            target_record_id = entity_id,
            actor_id         = actor_id,
            actor_role       = actor_role,
            metadata         = {
                "entity_type":  label,
                "entity_value": value,
                "db_hit_count": hits.db_hit_count,
                "entity_score": hits.entity_score,
                "fir_id":       fir_id,
            },
        )

        all_entity_hits.append(hits)
        logger.debug(
            "  %-20s %-10s tables_hit=%d score=%.4f",
            value[:20], label, hits.db_hit_count, hits.entity_score,
        )

    db.flush()

    result = CrossLookupResult(
        fir_id         = fir_id,
        total_entities = len(all_entity_hits),
        entity_hits    = all_entity_hits,
    )

    logger.info(
        "Cross-lookup done | fir_id=%s | entities=%d | tables_hit_sum=%d",
        fir_id,
        result.total_entities,
        sum(e.db_hit_count for e in result.entity_hits),
    )
    return result


# ─────────────────────────────────────────────
# Convenience serializer  →  ready for Groq
# ─────────────────────────────────────────────

def result_to_groq_payload(result: CrossLookupResult) -> dict[str, Any]:
    """
    Convert CrossLookupResult into a clean dict.
    that you pass directly into the Groq prompt builder (Step 5).
    """
    entities_payload = []
    for h in result.entity_hits:
        entities_payload.append({
            "entity_type":  h.entity_type,
            "entity_value": h.entity_value,
            "entity_score": h.entity_score,
            "db_hit_count": h.db_hit_count,
            "hits": {
                "contact":      h.contact_hits,
                "bank":         h.bank_hits,
                "crime":        h.crime_hits,
                "surveillance": h.surveillance_hits,
                "social":       h.social_hits,
                "other_firs":   h.fir_hits,
            },
        })

    return {
        "fir_id":        result.fir_id,
        "total_entities": result.total_entities,
        "processed_at":  result.processed_at.isoformat(),
        "entities":      entities_payload,
    }
