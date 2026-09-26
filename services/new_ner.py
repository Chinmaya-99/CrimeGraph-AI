"""
backend/services/ner.py
================================================================

SIH26189 - Hybrid FIR Named Entity Recognition

Architecture
------------

                    FIR TEXT
                       |
                       v
               Text normalization
                       |
             +---------+---------+
             |                   |
             v                   v
        spaCy en_core_web_lg   Regex/domain
             |                   |
             |             +-----+------------------+
             |             |     |      |     |     |
             |           PHONE VEHICLE FIR CASE MONEY ACCOUNT
             |
             v
      Generic validation
             |
       +-----+------+----------------+
       |            |                |
       v            v                v
   Blocklist     Gazetteer      Context rules
       |            |                |
       +------------+----------------+
                    |
                    v
             Conflict resolution
                    |
                    v
               Deduplication
                    |
                    v
             Final validation
                    |
                    v
             Clean entities

Important
---------
This module intentionally contains NO project-specific people,
phone numbers, vehicles, organizations, or locations.

The database remains the source of truth for identities and
relationships.

Supported application entity types
-----------------------------------
    PERSON
    PHONE
    VEHICLE
    LOCATION
    ORGANIZATION
    ACCOUNT
    FIR_NUMBER
    CASE_ID
    MONEY

spaCy model
-----------
    en_core_web_lg

Install:
    python -m spacy download en_core_web_lg

Gazetteer
---------
Optional file:

    backend/data/india_gazetteer.txt

One place per line.

The gazetteer is evidence for LOCATION classification. It does
NOT blindly override contextual information.

Compatibility
-------------
The following public functions are preserved for the rest of the
application:

    extract_entities()
    get_entity_type()
    get_entity_text()
    normalize_phone_digits()
    normalize_vehicle_plate()
    normalize_text()
    extract_phones()
    extract_vehicles()
    extract_fir_numbers()
    extract_case_ids()
    extract_money()
    extract_accounts()
"""


from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable


import spacy


# ================================================================
# LOGGING
# ================================================================

logger = logging.getLogger(__name__)


# ================================================================
# PATHS
# ================================================================

SERVICES_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SERVICES_DIR.parent

GAZETTEER_FILE = (
    BACKEND_DIR
    / "data_base"
    / "india_gazetteer.txt"
)


# ================================================================
# SPACY MODEL
# ================================================================

MODEL_NAME = "en_core_web_lg"


def _load_spacy_model():
    """
    Load the configured spaCy model exactly once.

    We intentionally fail clearly if the model is missing instead
    of silently falling back to en_core_web_sm.

    Reason:
        Idea 1 explicitly uses en_core_web_lg as the baseline.
    """

    try:
        return spacy.load(
            MODEL_NAME
        )

    except OSError as exc:

        raise RuntimeError(
            "\n"
            f"spaCy model '{MODEL_NAME}' is not installed.\n\n"
            "Install it with:\n\n"
            f"    python -m spacy download {MODEL_NAME}\n\n"
            "Then restart the backend.\n"
        ) from exc


_nlp = None

def get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = _load_spacy_model()
    return _nlp


# ================================================================
# APPLICATION ENTITY TYPES
# ================================================================

PERSON = "PERSON"
PHONE = "PHONE"
VEHICLE = "VEHICLE"
LOCATION = "LOCATION"
ORGANIZATION = "ORGANIZATION"
ACCOUNT = "ACCOUNT"
FIR_NUMBER = "FIR_NUMBER"
CASE_ID = "CASE_ID"
MONEY = "MONEY"


# ================================================================
# SPACY LABELS
# ================================================================

SPACY_PERSON = "PERSON"
SPACY_ORG = "ORG"
SPACY_GPE = "GPE"
SPACY_LOC = "LOC"


# ================================================================
# ENTITY PRIORITY
# ================================================================
#
# Higher value = stronger semantic precedence when two extractors
# disagree about the same text.
#
# Example:
#
#   spaCy: Cuttack -> PERSON
#   Gazetteer/context: Cuttack -> LOCATION
#
# LOCATION wins.
# ================================================================

ENTITY_PRIORITY = {
    PHONE: 100,
    VEHICLE: 100,
    FIR_NUMBER: 100,
    CASE_ID: 100,
    MONEY: 100,
    ACCOUNT: 100,

    PERSON: 80,
    ORGANIZATION: 70,
    LOCATION: 65,
}


# ================================================================
# GENERIC FIR / POLICE BLOCKLIST
# ================================================================
#
# These are domain vocabulary, NOT project-specific entities.
#
# They exist because general English NER models can classify
# document headings such as "Complainant" or "Time of Incident"
# as entities.
# ================================================================

ENTITY_BLOCKLIST = {
    # FIR/document headings
    "fir",
    "first information report",
    "fir no",
    "fir number",
    "case id",
    "case number",
    "case no",
    "registration",
    "date of registration",
    "date of incident",
    "time of incident",
    "incident",
    "incident location",
    "description",
    "description of incident",
    "preliminary investigation",
    "investigation",
    "investigation details",
    "investigation findings",
    "status",

    # Person-related field labels
    "complainant",
    "complainant name",
    "accused",
    "accused person",
    "accused persons",
    "suspect",
    "suspect person",
    "suspects",
    "victim",
    "victim name",
    "witness",
    "witness name",
    "person",
    "persons",
    "persons mentioned",
    "person mentioned",
    "name",
    "designation",
    "rank",
    "role",
    "officer",
    "investigating officer",

    # Contact fields
    "contact",
    "contact number",
    "contact numbers",
    "phone",
    "phone number",
    "mobile",
    "mobile number",
    "telephone",
    "telephone number",

    # Vehicle fields
    "vehicle",
    "vehicle number",
    "registration number",
    "registration no",
    "registration plate",
    "license plate",

    # Organization fields
    "organization",
    "organization name",
    "organizations",
    "company",
    "company name",
    "bank",
    "bank name",

    # Geographic fields
    "location",
    "locations",
    "district",
    "state",
    "city",
    "village",
    "address",
    "place",

    # Administrative fields
    "police station",
    "station",
    "department",
    "date",
    "time",
    "day",
    "month",
    "year",
}


# ================================================================
# BLOCKLIST FRAGMENTS
# ================================================================
#
# Exact blocklist catches complete labels.
# Fragment blocklist catches malformed PDF NER spans such as:
#
#     "Odisha Date of Registration"
#
# ================================================================

BLOCKLIST_FRAGMENTS = (
    "date of registration",
    "date of incident",
    "time of incident",
    "description of incident",
    "persons mentioned",
    "contact numbers",
    "contact number",
    "registration number",
    "registration no",
    "case id",
    "fir number",
    "fir no",
    "investigating officer",
)


# ================================================================
# POLICE / GOVERNMENT DESIGNATIONS
# ================================================================
#
# Generic vocabulary only.
# No specific officer names are included.
# ================================================================

DESIGNATIONS = {
    "si",
    "s.i.",
    "s.i",
    "sub inspector",
    "sub-inspector",
    "subinspector",
    "asi",
    "a.s.i.",
    "a.s.i",
    "assistant sub inspector",
    "assistant sub-inspector",
    "inspector",
    "police inspector",
    "head constable",
    "constable",
    "hc",
    "h.c.",
    "assistant inspector",
    "deputy superintendent",
    "deputy superintendent of police",
    "dsp",
    "d.s.p.",
    "assistant commissioner",
    "assistant commissioner of police",
    "acp",
    "a.c.p.",
    "commissioner",
    "commissioner of police",
    "superintendent",
    "superintendent of police",
    "sp",
    "s.p.",
    "additional superintendent",
    "additional superintendent of police",
    "director general",
    "director general of police",
    "dgp",
    "d.g.p.",
}


# ================================================================
# INDIAN STATES / UNION TERRITORIES
# ================================================================
#
# This is a deterministic fallback, not a complete city gazetteer.
# Full geographic data can be placed in india_gazetteer.txt.
# ================================================================

INDIAN_STATES_AND_UTS = {
    "andhra pradesh",
    "arunachal pradesh",
    "assam",
    "bihar",
    "chhattisgarh",
    "goa",
    "gujarat",
    "haryana",
    "himachal pradesh",
    "jharkhand",
    "karnataka",
    "kerala",
    "madhya pradesh",
    "maharashtra",
    "manipur",
    "meghalaya",
    "mizoram",
    "nagaland",
    "odisha",
    "orissa",
    "punjab",
    "rajasthan",
    "sikkim",
    "tamil nadu",
    "telangana",
    "tripura",
    "uttar pradesh",
    "uttarakhand",
    "west bengal",
    "andaman and nicobar islands",
    "chandigarh",
    "dadra and nagar haveli and daman and diu",
    "delhi",
    "jammu and kashmir",
    "ladakh",
    "lakshadweep",
    "puducherry",
}


# ================================================================
# GENERIC GEOGRAPHIC HINTS
# ================================================================

LOCATION_HINTS = {
    "road",
    "street",
    "lane",
    "chowk",
    "square",
    "railway",
    "railway station",
    "bus stand",
    "airport",
    "market",
    "village",
    "town",
    "district",
    "city",
    "nagar",
    "colony",
    "sector",
    "ward",
    "junction",
    "crossing",
    "highway",
    "hospital",
    "temple",
    "port",
    "warehouse",
    "bridge",
    "station road",
}


# ================================================================
# ORGANIZATION HINTS
# ================================================================

ORGANIZATION_HINTS = {
    "pvt",
    "pvt.",
    "private",
    "ltd",
    "ltd.",
    "limited",
    "llp",
    "inc",
    "inc.",
    "corp",
    "corp.",
    "corporation",
    "company",
    "logistics",
    "traders",
    "trading",
    "exports",
    "transport",
    "network",
    "industries",
    "enterprises",
    "services",
    "solutions",
    "bank",
    "finance",
    "financial",
    "insurance",
    "telecom",
    "department",
    "ministry",
    "government",
    "authority",
    "commission",
    "police",
}


# ================================================================
# COMMON NAME PREFIXES
# ================================================================

NAME_PREFIXES = {
    "mr",
    "mr.",
    "mrs",
    "mrs.",
    "ms",
    "ms.",
    "miss",
    "dr",
    "dr.",
}


# ================================================================
# GAZETTEER LOADING
# ================================================================

def _normalize_lookup_text(
    value: str,
) -> str:
    """
    Normalize text for dictionary comparison.
    """

    value = (
        value
        .replace("\u00a0", " ")
        .strip()
        .lower()
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value


def _load_gazetteer() -> set[str]:
    """
    Load geographic names from the optional gazetteer file.

    File format
    -----------
    One place per line.

    Blank lines and lines beginning with '#' are ignored.

    Example:

        Cuttack
        Bhubaneswar
        Puri
        Rourkela

    No project-specific place is required in the Python source.
    """

    gazetteer = {
        _normalize_lookup_text(value)
        for value in INDIAN_STATES_AND_UTS
    }

    if not GAZETTEER_FILE.exists():
        logger.warning(
            "Gazetteer file not found: %s. "
            "Using built-in Indian states/UTs only.",
            GAZETTEER_FILE,
        )

        return gazetteer

    try:

        with GAZETTEER_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            for raw_line in file:

                line = raw_line.strip()

                if not line:
                    continue

                if line.startswith("#"):
                    continue

                gazetteer.add(
                    _normalize_lookup_text(line)
                )

    except OSError:
        logger.exception(
            "Failed to load gazetteer: %s",
            GAZETTEER_FILE,
        )

    logger.info(
        "Loaded %d gazetteer entries",
        len(gazetteer),
    )

    return gazetteer


GAZETTEER = _load_gazetteer()


# ================================================================
# BASIC PUBLIC HELPERS
# ================================================================

def get_entity_type(
    entity: dict,
) -> str:
    """
    Return canonical entity type.

    Supports both:
        entity["type"]
    and:
        entity["label"]

    for compatibility with existing code.
    """

    value = (
        entity.get("type")
        or entity.get("label")
        or "UNKNOWN"
    )

    return str(
        value
    ).strip().upper()


def get_entity_text(
    entity: dict,
) -> str:
    """
    Return entity text.
    """

    return str(
        entity.get("text")
        or ""
    ).strip()


# ================================================================
# PHONE NORMALIZATION
# ================================================================

def normalize_phone_digits(
    value: str,
) -> str:
    """
    Normalize a phone value to the last 10 digits.

    Examples
    --------
        +91 98765 43210
        98765-43210

    ->

        9876543210
    """

    digits = re.sub(
        r"\D",
        "",
        value or "",
    )

    if len(digits) >= 10:
        return digits[-10:]

    return digits


# ================================================================
# VEHICLE NORMALIZATION
# ================================================================

def normalize_vehicle_plate(
    value: str,
) -> str:
    """
    Normalize an Indian registration number to alphanumeric form.

    Example
    -------
        OD-05-AB-1234
        OD 05 AB 1234
        OD05AB1234

    all normalize to:

        OD05AB1234
    """

    return re.sub(
        r"[^A-Z0-9]",
        "",
        (value or "").upper(),
    )


# ================================================================
# GENERAL TEXT NORMALIZATION
# ================================================================

def normalize_text(
    text: str,
) -> str:
    """
    Normalize PDF-extracted text.

    Important:
        Newlines are preserved where useful for field/section
        extraction.

    We do not blindly collapse the entire document into one line.
    """

    if not text:
        return ""

    text = text.replace(
        "\u00a0",
        " ",
    )

    # Zero-width characters commonly introduced by PDFs.
    text = text.replace(
        "\u200b",
        "",
    )
    text = text.replace(
        "\u200c",
        "",
    )
    text = text.replace(
        "\u200d",
        "",
    )

    # Normalize common Unicode dash variants.
    for dash in (
        "\u2010",
        "\u2011",
        "\u2012",
        "\u2013",
        "\u2014",
        "\u2212",
        "\ufe58",
        "\ufe63",
        "\uff0d",
    ):
        text = text.replace(
            dash,
            "-",
        )

    # Normalize the common OCR/PDF case:
    #
    # CR￾88/2024
    #
    # into:
    #
    # CR-88/2024
    text = re.sub(
        r"(?i)\bCR\s*[\W_]*\s*(\d+)\s*/\s*(\d{4})\b",
        r"CR-\1/\2",
        text,
    )

    # Remove control characters but retain newlines.
    text = re.sub(
        r"[\x00-\x08\x0b\x0c\x0e-\x1f]",
        " ",
        text,
    )

    # Normalize spaces within lines.
    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    # Remove excessive blank lines.
    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


def _flat_text(
    text: str,
) -> str:
    """
    One-line representation for regex extraction.
    """

    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


# ================================================================
# BLOCKLIST FUNCTIONS
# ================================================================

def _is_blocklisted(
    value: str,
) -> bool:
    """
    Determine whether a candidate is actually document vocabulary
    rather than an entity.
    """

    key = _normalize_lookup_text(
        value
    )

    if not key:
        return True

    if key in ENTITY_BLOCKLIST:
        return True

    for fragment in BLOCKLIST_FRAGMENTS:

        if fragment in key:
            return True

    return False


# ================================================================
# DESIGNATION STRIPPING
# ================================================================

def _strip_designation(
    value: str,
) -> str:
    """
    Remove generic professional/police designations from the
    beginning of a person's name.

    Examples
    --------
        Inspector Anil Das
        -> Anil Das

        SI Rahul Kumar
        -> Rahul Kumar
    """

    value = re.sub(
        r"\s+",
        " ",
        value or "",
    ).strip()

    if not value:
        return ""

    # Longest first avoids:
    #
    # "sub inspector"
    #
    # being partially processed as:
    #
    # "inspector".
    ordered = sorted(
        DESIGNATIONS,
        key=len,
        reverse=True,
    )

    changed = True

    while changed:

        changed = False

        for designation in ordered:

            pattern = (
                r"^\s*"
                + re.escape(designation)
                + r"\s*[,.:;-]?\s+"
            )

            if re.match(
                pattern,
                value,
                flags=re.IGNORECASE,
            ):

                value = re.sub(
                    pattern,
                    "",
                    value,
                    count=1,
                    flags=re.IGNORECASE,
                ).strip()

                changed = True
                break

    return value


# ================================================================
# PERSON VALIDATION
# ================================================================

def _looks_like_name_word(
    word: str,
) -> bool:
    """
    Validate one name token.
    """

    word = word.strip(
        ".,;:()[]{}"
    )

    return bool(
        re.fullmatch(
            r"[A-Za-z]+(?:['-][A-Za-z]+)*",
            word,
        )
    )


def _is_valid_person(
    value: str,
) -> bool:
    """
    Conservative PERSON validation.

    Generic spaCy candidates must look like actual names rather than
    document headings.

    We deliberately require at least two name tokens.
    """

    if not value:
        return False

    value = _strip_designation(
        value
    )

    if _is_blocklisted(
        value
    ):
        return False

    key = _normalize_lookup_text(
        value
    )

    # Geographic names should not be accepted as people if they
    # exactly match a gazetteer entry.
    if key in GAZETTEER:
        return False

    # No numeric identifiers.
    if re.search(
        r"\d",
        value,
    ):
        return False

    words = value.split()

    if not 2 <= len(words) <= 5:
        return False

    if not all(
        _looks_like_name_word(word)
        for word in words
    ):
        return False

    # Avoid obvious administrative fragments.
    forbidden = (
    "date",
    "time",
    "description",
    "registration",
    "incident",
    "police station",
    "case",
    "fir",
    "contact",
    "number",
    "location",
    "organization",
    "vehicle",
    "complainant",
    "accused",
    "witness",
    "victim",
    "suspect",
)

    if any(
        fragment in key
        for fragment in forbidden
    ):
        return False

    return True


# ================================================================
# ORGANIZATION VALIDATION
# ================================================================

def _is_valid_organization(
    value: str,
) -> bool:
    """
    Conservative organization validation.
    """

    if not value:
        return False

    value = value.strip(
        " ,.;:"
    )

    if _is_blocklisted(
        value
    ):
        return False

    key = _normalize_lookup_text(
        value
    )

    if key in GAZETTEER:
        return False

    if re.search(
        r"\d",
        value,
    ):
        return False

    # Organization indicators provide strong evidence.
    if any(
        re.search(
            rf"\b{re.escape(hint)}\b",
            key,
        )
        for hint in ORGANIZATION_HINTS
    ):
        return True

    words = value.split()

    # Generic spaCy ORG predictions without organization vocabulary
    # are accepted only if they look like a plausible proper-name
    # phrase.
    if not 2 <= len(words) <= 7:
        return False

    if not all(
        re.fullmatch(
            r"[A-Za-z.&'/-]+",
            word.strip(","),
        )
        for word in words
    ):
        return False

    return True


# ================================================================
# LOCATION VALIDATION
# ================================================================

def _is_valid_location(
    value: str,
) -> bool:
    """
    Validate a geographic candidate.

    Evidence sources:
        1. Gazetteer
        2. State/UT list
        3. Geographic context words
        4. Explicit location fields

    This function itself does not know whether a particular place
    belongs to our seeded fake dataset.
    """

    if not value:
        return False

    value = value.strip(
        " ,.;:"
    )

    if _is_blocklisted(
        value
    ):
        return False

    key = _normalize_lookup_text(
        value
    )

    if key in GAZETTEER:
        return True

    if key in INDIAN_STATES_AND_UTS:
        return True

    # Explicit geographic descriptor.
    if any(
        hint in key
        for hint in LOCATION_HINTS
    ):
        return True

    # Generic one/two-word geographic candidates can be accepted
    # only when supplied by a strong contextual extractor.
    words = value.split()

    if 1 <= len(words) <= 6:
        return all(
            re.fullmatch(
                r"[A-Za-z.'-]+",
                word.strip(","),
            )
            for word in words
        )

    return False


# ================================================================
# PHONE EXTRACTION
# ================================================================

def extract_phones(
    text: str,
) -> list[str]:
    """
    Extract Indian mobile numbers.

    Supported:
        9876543210
        +91 98765 43210
        +91-98765-43210
        98765-43210
    """

    if not text:
        return []

    pattern = (
        r"(?<!\d)"
        r"(?:\+91[\s\-]*)?"
        r"[6-9]"
        r"(?:[\s\-]?\d){9}"
        r"(?!\d)"
    )

    found = []
    seen = set()

    for raw in re.findall(
        pattern,
        text,
    ):

        digits = normalize_phone_digits(
            raw
        )

        if (
            len(digits) == 10
            and digits[0] in "6789"
            and digits not in seen
        ):
            seen.add(
                digits
            )

            found.append(
                digits
            )

    return found


# ================================================================
# VEHICLE EXTRACTION
# ================================================================

def extract_vehicles(
    text: str,
) -> list[str]:
    """
    Extract Indian vehicle registration numbers.

    Examples:
        OD-05-AB-1234
        OD05AB1234
        OD 05 AB 1234
    """

    if not text:
        return []

    pattern = (
        r"(?<![A-Z0-9])"
        r"[A-Z]{2}"
        r"[-\s]?"
        r"\d{1,2}"
        r"[-\s]?"
        r"[A-Z]{1,3}"
        r"[-\s]?"
        r"\d{4}"
        r"(?![A-Z0-9])"
    )

    matches = re.findall(
        pattern,
        text.upper(),
    )

    results = []
    seen = set()

    for vehicle in matches:

        dashed = re.sub(
            r"[\s\-]+",
            "-",
            vehicle.strip("-"),
        )

        key = normalize_vehicle_plate(
            dashed
        )

        if key and key not in seen:

            seen.add(
                key
            )

            results.append(
                dashed
            )

    return results


# ================================================================
# FIR NUMBER EXTRACTION
# ================================================================

def extract_fir_numbers(
    text: str,
) -> list[str]:
    """
    Extract FIR numbers when explicitly introduced by an FIR label.

    Example:
        FIR No.: 127/2026
    """

    if not text:
        return []

    pattern = (
        r"\bFIR\s*"
        r"(?:No\.?|Number)"
        r"\s*[:#\-]?\s*"
        r"([A-Z0-9]+(?:[-/][A-Z0-9]+)*)"
    )

    results = []
    seen = set()

    for value in re.findall(
        pattern,
        text,
        flags=re.IGNORECASE,
    ):

        value = value.strip()

        if not re.search(
            r"\d",
            value,
        ):
            continue

        key = value.lower()

        if key not in seen:

            seen.add(
                key
            )

            results.append(
                value
            )

    return results


# ================================================================
# CASE ID EXTRACTION
# ================================================================
def extract_case_ids(
    text: str,
) -> list[str]:
    """
    Extract case identifiers using generic case-ID context.

    Supported examples:

        Case ID: TEST-CRIME-2026-001
        Case ID: SIH-CRIME-2026-0042
        Case Number: CR-88/2024
        CR-88/2024

    Important:
        The extractor does NOT assume a project-specific prefix.
    """

    if not text:
        return []

    results = []
    seen = set()

    # ------------------------------------------------------------
    # 1. Explicit case fields.
    #
    # This is the strongest signal because the document itself
    # tells us that the value is a case identifier.
    # ------------------------------------------------------------

    explicit_pattern = (
        r"(?im)^\s*"
        r"(?:case\s*(?:id|number|no\.?)|"
        r"case\s*reference)"
        r"\s*[:#\-]\s*"
        r"([A-Z0-9][A-Z0-9/_-]{2,80})"
        r"\s*$"
    )

    for raw in re.findall(
        explicit_pattern,
        text,
    ):

        value = _normalize_case_id(
            raw
        )

        if not value:
            continue

        key = value.lower()

        if key not in seen:

            seen.add(key)
            results.append(value)

    # ------------------------------------------------------------
    # 2. Generic CR-style case identifiers.
    #
    # Example:
    #
    #     CR-88/2024
    #     CR- 88/2024
    # ------------------------------------------------------------

    cr_pattern = (
        r"\bCR-\s*\d+\s*/\s*\d{4}\b"
    )

    for raw in re.findall(
        cr_pattern,
        text,
        flags=re.IGNORECASE,
    ):

        value = _normalize_case_id(
            raw
        )

        key = value.lower()

        if key not in seen:

            seen.add(key)
            results.append(value)

    return results


def _normalize_case_id(
    value: str,
) -> str:
    """
    Normalize supported case identifiers.
    """

    value = re.sub(
        r"\s+",
        " ",
        value or "",
    ).strip()

    match = re.fullmatch(
        r"CR-\s*(\d+)\s*/\s*(\d{4})",
        value,
        flags=re.IGNORECASE,
    )

    if match:

        return (
            f"CR-{match.group(1)}"
            f"/{match.group(2)}"
        )

    if value.upper().startswith(
        "SIH-"
    ):
        return re.sub(
            r"\s+",
            "",
            value,
        ).upper()

    return value


# ================================================================
# MONEY EXTRACTION
# ================================================================

def extract_money(
    text: str,
) -> list[str]:
    """
    Extract Indian currency values.

    Examples:
        ₹2,35,000
        ₹ 2,35,000
        Rs. 235000
        Rs 2,35,000
        INR 235000
    """

    if not text:
        return []

    pattern = (
        r"(?<!\w)"
        r"(?:₹|Rs\.?|INR)"
        r"\s*"
        r"(?:"
        r"\d{1,3}(?:,\d{2,3})+"
        r"|"
        r"\d+"
        r")"
        r"(?:\.\d{1,2})?"
        r"(?!\w)"
    )

    results = []
    seen = set()

    for raw in re.findall(
        pattern,
        text,
        flags=re.IGNORECASE,
    ):

        value = re.sub(
            r"\s+",
            " ",
            raw,
        ).strip()

        key = value.lower()

        if key not in seen:

            seen.add(
                key
            )

            results.append(
                value
            )

    return results


# ================================================================
# ACCOUNT EXTRACTION
# ================================================================

def extract_accounts(
    text: str,
) -> list[str]:
    """
    Extract account numbers only when account context exists.

    Examples:
        Account Number: 90010020001
        A/C No: 90010020001
        Account ID: 90010020001
    """

    if not text:
        return []

    patterns = [
        (
            r"\b(?:account|a/c)\s*"
            r"(?:number|no\.?|num)?\s*"
            r"[:#\-]?\s*"
            r"(\d{8,18})\b"
        ),
        (
            r"\baccount\s*id\s*"
            r"[:#\-]?\s*"
            r"(\d{8,18})\b"
        ),
    ]

    results = []
    seen = set()

    for pattern in patterns:

        for raw in re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            digits = re.sub(
                r"\D",
                "",
                raw,
            )

            if (
                8 <= len(digits) <= 18
                and digits not in seen
            ):

                seen.add(
                    digits
                )

                results.append(
                    digits
                )

    return results


# ================================================================
# EXPLICIT FIELD EXTRACTION
# ================================================================

def _extract_field_values(
    text: str,
    field_names: Iterable[str],
) -> list[str]:
    """
    Extract single-line field values.

    Example:
        District: Cuttack

    returns:
        ["Cuttack"]
    """

    if not text:
        return []

    alternatives = "|".join(
        re.escape(
            name
        )
        for name in field_names
    )

    pattern = (
        rf"(?im)^\s*"
        rf"(?:{alternatives})"
        rf"\s*[:\-]\s*"
        rf"(.+?)"
        rf"\s*$"
    )

    return [
        value.strip()
        for value in re.findall(
            pattern,
            text,
        )
        if value.strip()
    ]


def _extract_section_values(
    text: str,
    headers: Iterable[str],
) -> list[str]:
    """
    Extract simple line-based values from a FIR section.

    Example:

        Persons Mentioned
        Rahul Kumar
        Arjun Singh

    returns:

        Rahul Kumar
        Arjun Singh
    """

    lines = [
        line.strip()
        for line in text.splitlines()
    ]

    header_keys = {
        _normalize_lookup_text(
            header
        )
        for header in headers
    }

    stop_headers = {
        "contact numbers",
        "contact number",
        "vehicle",
        "organization",
        "organizations",
        "locations",
        "location",
        "status",
        "investigating officer",
        "police station",
        "date",
        "state",
        "district",
    }

    values = []
    active = False

    for line in lines:

        if not line:
            continue

        key = _normalize_lookup_text(
            line.rstrip(":")
        )

        if key in header_keys:

            active = True
            continue

        if not active:
            continue

        if key in stop_headers:
            break

        # Another field-like line usually means the section ended.
        if re.match(
            r"^[A-Za-z][A-Za-z0-9 /_-]{1,60}\s*:",
            line,
        ):
            break

        values.append(
            line
        )

    return values


# ================================================================
# STRUCTURED PERSON EXTRACTION
# ================================================================

def _extract_structured_people(
    text: str,
) -> list[str]:
    """
    Extract names from explicit FIR structures.

    Supported examples:
        Name: Inspector Anil Das
        Investigating Officer: Inspector Anil Das

        Persons Mentioned
        Rahul Kumar
        Arjun Singh
    """

    candidates = []

    candidates.extend(
    _extract_field_values(
        text,
        [
            "Name",
            "Complainant",
            "Complainant Name",
            "Accused",
            "Accused Name",
            "Witness",
            "Witness Name",
            "Victim",
            "Victim Name",
            "Investigating Officer",
        ],
    )
)
    

    candidates.extend(
        _extract_section_values(
            text,
            [
                "Persons Mentioned",
                "Person Mentioned",
            ],
        )
    )

    results = []
    seen = set()

    for candidate in candidates:

        candidate = _strip_designation(
            candidate
        )

        if not _is_valid_person(
            candidate
        ):
            continue

        key = _normalize_lookup_text(
            candidate
        )

        if key not in seen:

            seen.add(
                key
            )

            results.append(
                candidate
            )

    return results


# ================================================================
# STRUCTURED ORGANIZATION EXTRACTION
# ================================================================

def _extract_structured_organizations(
    text: str,
) -> list[str]:
    """
    Extract organizations from explicit organization/company fields.
    """

    candidates = []

    candidates.extend(
        _extract_field_values(
            text,
            [
                "Organization",
                "Organization Name",
                "Organization/Company",
                "Company",
            ],
        )
    )

    results = []
    seen = set()

    for candidate in candidates:

        candidate = candidate.strip(
            " ,.;:"
        )

        if not _is_valid_organization(
            candidate
        ):
            continue

        key = _normalize_lookup_text(
            candidate
        )

        if key not in seen:

            seen.add(
                key
            )

            results.append(
                candidate
            )

    return results


# ================================================================
# STRUCTURED LOCATION EXTRACTION
# ================================================================

def _extract_structured_locations(
    text: str,
) -> list[str]:
    """
    Extract locations from explicit FIR fields/sections.
    """

    candidates = []

    candidates.extend(
        _extract_field_values(
            text,
            [
                "District",
                "State",
                "Incident Location",
                "Location",
            ],
        )
    )

    candidates.extend(
        _extract_section_values(
            text,
            [
                "Locations",
                "Location Names",
            ],
        )
    )

    results = []
    seen = set()

    for candidate in candidates:

        candidate = candidate.strip(
            " ,.;:"
        )

        if not _is_valid_location(
            candidate
        ):
            continue

        key = _normalize_lookup_text(
            candidate
        )

        if key not in seen:

            seen.add(
                key
            )

            results.append(
                candidate
            )

    return results


# ================================================================
# CONTEXTUAL LOCATION EXTRACTION
# ================================================================

def _extract_context_locations(
    text: str,
) -> list[str]:
    """
    Extract locations from generic contextual phrases.

    Examples:
        resident of <place>
        lives in <place>
        located in <place>
        operates from <place>
        near <place>

    This is intentionally conservative.
    """

    patterns = [
        r"\bresident\s+of\s+([A-Z][A-Za-z .'-]{1,80})",
        r"\blives\s+in\s+([A-Z][A-Za-z .'-]{1,80})",
        r"\blocated\s+in\s+([A-Z][A-Za-z .'-]{1,80})",
        r"\boperates\s+from\s+([A-Z][A-Za-z .'-]{1,80})",
        r"\bnear\s+([A-Z][A-Za-z .'-]{1,80})",
        rf"\b(?:at|near|from|to|in|around)\s+"
        rf"([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*?"
        rf"\s+(?:Railway\s+Station|Police\s+Station|Bus\s+Stand|"
        rf"Airport|Junction|Road|Chowk|Market|Hospital|College|University))"
    ]

    results = []
    seen = set()

    for pattern in patterns:

        for raw in re.findall(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            candidate = raw.strip(
                " ,.;:"
            )

            # Stop common sentence continuations.
            candidate = re.split(
                r"\s+(?:was|were|is|are|and|who|which|that)\s+",
                candidate,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip()

            if not _is_valid_location(
                candidate
            ):
                continue

            key = _normalize_lookup_text(
                candidate
            )

            if key not in seen:

                seen.add(
                    key
                )

                results.append(
                    candidate
                )

    return results


# ================================================================
# SPACY ENTITY CONVERSION
# ================================================================

def _spacy_to_application_type(
    label: str,
) -> str | None:
    """
    Convert spaCy labels to application labels.
    """

    if label == SPACY_PERSON:
        return PERSON

    if label == SPACY_ORG:
        return ORGANIZATION

    if label in {
        SPACY_GPE,
        SPACY_LOC,
    }:
        return LOCATION

    return None


# ================================================================
# SPACY VALIDATION
# ================================================================

def _extract_spacy_entities(
    text: str,
) -> list[dict]:
    """
    Extract spaCy entities and validate them using generic FIR
    domain rules.

    spaCy is not blindly trusted.
    """

    if not text:
        return []

    doc = get_nlp()(text)

    results = []

    for ent in doc.ents:

        entity_type = _spacy_to_application_type(
            ent.label_
        )

        if entity_type is None:
            continue

        value = ent.text.strip()

        if not value:
            continue

        # --------------------------------------------------------
        # PERSON
        # --------------------------------------------------------

        if entity_type == PERSON:

            value = _strip_designation(
                value
            )

            if not _is_valid_person(
                value
            ):
                continue

            confidence = 0.90

        # --------------------------------------------------------
        # ORGANIZATION
        # --------------------------------------------------------

        elif entity_type == ORGANIZATION:

            if not _is_valid_organization(
                value
            ):
                continue

            confidence = 0.86

        # --------------------------------------------------------
        # LOCATION
        # --------------------------------------------------------

        else:

            # Gazetteer gives stronger geographic evidence.
            key = _normalize_lookup_text(
                value
            )

            if not _is_valid_location(
                value
            ):
                continue

            if key in GAZETTEER:
                confidence = 0.96
            else:
                confidence = 0.84

        results.append(
            {
                "text": value,
                "type": entity_type,
                "label": entity_type,
                "source": "spacy",
                "confidence": confidence,
            }
        )

    return results


# ================================================================
# ENTITY CREATION
# ================================================================

def add_entity(
    entities: list[dict],
    text: str,
    entity_type: str,
    source: str,
    confidence: float | None = None,
) -> None:
    """
    Add an entity in the canonical project format.

    Existing callers can continue using the original four
    parameters. Confidence is optional.
    """

    text = (
        text
        or ""
    ).strip()

    if not text:
        return

    entity_type = (
        entity_type
        or "UNKNOWN"
    ).strip().upper()

    item = {
        "text": text,
        "type": entity_type,
        "label": entity_type,
        "source": source,
    }

    if confidence is not None:
        item["confidence"] = round(
            float(confidence),
            4,
        )

    entities.append(
        item
    )


# ================================================================
# SOURCE CONFIDENCE
# ================================================================

SOURCE_CONFIDENCE = {
    "regex": 0.99,
    "structured": 0.97,
    "gazetteer": 0.96,
    "spacy": 0.84,
}


# ================================================================
# NORMALIZE ENTITY VALUE
# ================================================================

def _normalize_entity_value(
    value: str,
    entity_type: str,
) -> str:
    """
    Normalize an entity according to its type.

    The original extracted text remains available in `text`.
    """

    value = value.strip()

    if entity_type == PHONE:
        return normalize_phone_digits(
            value
        )

    if entity_type == VEHICLE:
        return normalize_vehicle_plate(
            value
        )

    if entity_type == CASE_ID:
        return _normalize_case_id(
            value
        )

    if entity_type == PERSON:
        return _strip_designation(
            value
        )
    if entity_type == ORGANIZATION:
        return re.sub(
            r"\s+",
            " ",
            value.strip(" ,.;:"),
    )
        

    return re.sub(
        r"\s+",
        " ",
        value,
    )


# ================================================================
# CONFLICT RESOLUTION
# ================================================================

def _resolve_conflicts(
    entities: list[dict],
) -> list[dict]:
    """
    Resolve conflicting classifications.

    Example:
        Cuttack -> PERSON
        Cuttack -> ORGANIZATION
        Cuttack -> LOCATION

    If deterministic/contextual evidence says LOCATION, the
    location classification wins.

    No project-specific names are used.
    """

    grouped: dict[
        str,
        list[dict],
    ] = {}

    for entity in entities:

        value = get_entity_text(
            entity
        )

        if not value:
            continue

        entity_type = get_entity_type(
            entity
        )

        normalized = _normalize_entity_value(
            value,
            entity_type,
        )

        key = (
            entity_type,
            normalized.lower(),
        )

        grouped.setdefault(
            normalized.lower(),
            [],
        ).append(
            {
                **entity,
                "_normalized": normalized,
                "_key": key,
            }
        )

    resolved = []

    for _, candidates in grouped.items():

        # --------------------------------------------------------
        # Prefer deterministic/structured evidence over spaCy.
        # --------------------------------------------------------

        best = max(
            candidates,
            key=lambda entity: (
                1
                if entity.get("source")
                in {
                    "regex",
                    "structured",
                    "gazetteer",
                }
                else 0,

                ENTITY_PRIORITY.get(
                    get_entity_type(entity),
                    0,
                ),

                float(
                    entity.get(
                        "confidence",
                        SOURCE_CONFIDENCE.get(
                            entity.get(
                                "source"
                            ),
                            0.5,
                        ),
                    )
                ),
            ),
        )

        # --------------------------------------------------------
        # If the same text has conflicting types and is a known
        # geographic name, LOCATION wins.
        # --------------------------------------------------------

        candidate_types = {
            get_entity_type(
                entity
            )
            for entity in candidates
        }

        if (
            len(candidate_types) > 1
            and best["_normalized"].lower()
            in GAZETTEER
        ):

            location_candidates = [
                entity
                for entity in candidates
                if get_entity_type(entity)
                == LOCATION
            ]

            if location_candidates:

                best = max(
                    location_candidates,
                    key=lambda entity: float(
                        entity.get(
                            "confidence",
                            0.0,
                        )
                    ),
                )

        cleaned = {
            key: value
            for key, value in best.items()
            if not key.startswith("_")
        }

        # Add normalized value for downstream matching.
        cleaned[
            "normalized_value"
        ] = best["_normalized"]

        resolved.append(
            cleaned
        )

    return resolved


# ================================================================
# DEDUPLICATION
# ================================================================

def _deduplicate_entities(
    entities: list[dict],
) -> list[dict]:
    """
    Deduplicate entities by:
        normalized_value + entity_type

    If duplicate evidence exists, keep the strongest source.
    """

    best: dict[
        tuple[str, str],
        dict,
    ] = {}

    for entity in entities:

        entity_type = get_entity_type(
            entity
        )

        value = get_entity_text(
            entity
        )

        if not value:
            continue

        normalized = entity.get(
            "normalized_value"
        )

        if not normalized:
            normalized = _normalize_entity_value(
                value,
                entity_type,
            )

        key = (
            entity_type,
            normalized.lower(),
        )

        current = best.get(
            key
        )

        if current is None:

            best[key] = {
                **entity,
                "normalized_value": normalized,
            }

            continue

        current_strength = (
            1
            if current.get("source")
            in {
                "regex",
                "structured",
                "gazetteer",
            }
            else 0
        )

        new_strength = (
            1
            if entity.get("source")
            in {
                "regex",
                "structured",
                "gazetteer",
            }
            else 0
        )

        current_confidence = float(
            current.get(
                "confidence",
                SOURCE_CONFIDENCE.get(
                    current.get(
                        "source"
                    ),
                    0.5,
                ),
            )
        )

        new_confidence = float(
            entity.get(
                "confidence",
                SOURCE_CONFIDENCE.get(
                    entity.get(
                        "source"
                    ),
                    0.5,
                ),
            )
        )

        if (
            new_strength > current_strength
            or (
                new_strength
                == current_strength
                and new_confidence
                > current_confidence
            )
        ):

            best[key] = {
                **entity,
                "normalized_value": normalized,
            }

    return list(
        best.values()
    )


# ================================================================
# FINAL VALIDATION
# ================================================================

def _final_validate(
    entities: list[dict],
) -> list[dict]:
    """
    Final safety gate before entities enter the database and
    cross-lookup pipeline.
    """

    validated = []

    for entity in entities:

        entity_type = get_entity_type(
            entity
        )

        text = get_entity_text(
            entity
        )

        normalized = entity.get(
            "normalized_value"
        ) or _normalize_entity_value(
            text,
            entity_type,
        )

        if not text:
            continue

        if _is_blocklisted(
            text
        ):
            continue

        # --------------------------------------------------------
        # PERSON
        # --------------------------------------------------------

        if entity_type == PERSON:

            if not _is_valid_person(
                text
            ):
                continue

        # --------------------------------------------------------
        # ORGANIZATION
        # --------------------------------------------------------

        elif entity_type == ORGANIZATION:

            if not _is_valid_organization(
                text
            ):
                continue

        # --------------------------------------------------------
        # LOCATION
        # --------------------------------------------------------

        elif entity_type == LOCATION:

            if not _is_valid_location(
                text
            ):
                continue

        # --------------------------------------------------------
        # PHONE
        # --------------------------------------------------------

        elif entity_type == PHONE:

            if not re.fullmatch(
                r"[6-9]\d{9}",
                normalized,
            ):
                continue

        # --------------------------------------------------------
        # VEHICLE
        # --------------------------------------------------------

        elif entity_type == VEHICLE:

            if not re.fullmatch(
                r"[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}",
                normalized,
            ):
                continue

        # --------------------------------------------------------
        # ACCOUNT
        # --------------------------------------------------------

        elif entity_type == ACCOUNT:

            if not re.fullmatch(
                r"\d{8,18}",
                normalized,
            ):
                continue

        # --------------------------------------------------------
        # FIR NUMBER
        # --------------------------------------------------------

        elif entity_type == FIR_NUMBER:

            if not re.search(
                r"\d",
                normalized,
            ):
                continue

        # --------------------------------------------------------
        # CASE ID
        # --------------------------------------------------------

        elif entity_type == CASE_ID:

            if not re.search(
                r"\d",
                normalized,
            ):
                continue

        # --------------------------------------------------------
        # MONEY
        # --------------------------------------------------------

        elif entity_type == MONEY:

            if not re.search(
                r"\d",
                normalized,
            ):
                continue

        else:
            continue

        # --------------------------------------------------------
        # Ensure confidence exists.
        # --------------------------------------------------------

        if "confidence" not in entity:

            entity[
                "confidence"
            ] = SOURCE_CONFIDENCE.get(
                entity.get(
                    "source"
                ),
                0.5,
            )

        entity[
            "confidence"
        ] = round(
            float(
                entity[
                    "confidence"
                ]
            ),
            4,
        )

        entity[
            "normalized_value"
        ] = normalized

        validated.append(
            entity
        )

    return validated


# ================================================================
# OUTPUT SORTING
# ================================================================

ENTITY_ORDER = {
    CASE_ID: 0,
    FIR_NUMBER: 1,
    PERSON: 2,
    PHONE: 3,
    VEHICLE: 4,
    ORGANIZATION: 5,
    LOCATION: 6,
    ACCOUNT: 7,
    MONEY: 8,
}


def _sort_entities(
    entities: list[dict],
) -> list[dict]:
    """
    Return deterministic entity ordering.
    """

    return sorted(
        entities,
        key=lambda entity: (
            ENTITY_ORDER.get(
                get_entity_type(entity),
                99,
            ),
            entity.get(
                "normalized_value",
                get_entity_text(entity),
            ).lower(),
        ),
    )


# ================================================================
# MAIN EXTRACTION FUNCTION
# ================================================================

def extract_entities(
    text: str,
) -> list[dict]:
    """
    Main hybrid FIR entity extraction function.

    Pipeline
    --------
        1. Normalize PDF text.
        2. Extract structured PERSON/ORG/LOCATION.
        3. Run en_core_web_lg.
        4. Validate spaCy predictions.
        5. Extract deterministic structured entities.
        6. Resolve conflicts.
        7. Deduplicate.
        8. Final validation.
        9. Stable sorting.

    Returns
    -------
    list[dict]

    Example
    -------
    {
        "text": "9876543210",
        "type": "PHONE",
        "label": "PHONE",
        "source": "regex",
        "confidence": 0.99,
        "normalized_value": "9876543210"
    }
    """

    if not text or not text.strip():
        return []

    # ------------------------------------------------------------
    # 1. Normalize PDF text.
    # ------------------------------------------------------------

    normalized_text = normalize_text(
        text
    )

    flat_text = _flat_text(
        normalized_text
    )

    entities: list[dict] = []

    # ------------------------------------------------------------
    # 2. Structured PERSON extraction.
    # ------------------------------------------------------------

    for person in _extract_structured_people(
        normalized_text
    ):

        add_entity(
            entities,
            person,
            PERSON,
            "structured",
            0.97,
        )

    # ------------------------------------------------------------
    # 3. Structured ORGANIZATION extraction.
    # ------------------------------------------------------------

    for organization in _extract_structured_organizations(
        normalized_text
    ):

        add_entity(
            entities,
            organization,
            ORGANIZATION,
            "structured",
            0.97,
        )

    # ------------------------------------------------------------
    # 4. Structured LOCATION extraction.
    # ------------------------------------------------------------

    for location in _extract_structured_locations(
        normalized_text
    ):

        source = (
            "gazetteer"
            if _normalize_lookup_text(location)
            in GAZETTEER
            else "structured"
        )

        confidence = (
            0.96
            if source == "gazetteer"
            else 0.97
        )

        add_entity(
            entities,
            location,
            LOCATION,
            source,
            confidence,
        )

    # ------------------------------------------------------------
    # 5. Contextual LOCATION extraction.
    # ------------------------------------------------------------

    for location in _extract_context_locations(
        normalized_text
    ):

        add_entity(
            entities,
            location,
            LOCATION,
            "structured",
            0.90,
        )

    # ------------------------------------------------------------
    # 6. spaCy en_core_web_lg.
    # ------------------------------------------------------------

    try:

        spacy_entities = _extract_spacy_entities(
            normalized_text
        )

        entities.extend(
            spacy_entities
        )

    except Exception:

        logger.exception(
            "spaCy NER extraction failed"
        )

        # Structured/regex extraction can still proceed.

    # ------------------------------------------------------------
    # 7. PHONE.
    # ------------------------------------------------------------

    for phone in extract_phones(
        flat_text
    ):

        add_entity(
            entities,
            phone,
            PHONE,
            "regex",
            0.99,
        )

    # ------------------------------------------------------------
    # 8. VEHICLE.
    # ------------------------------------------------------------

    for vehicle in extract_vehicles(
        flat_text
    ):

        add_entity(
            entities,
            vehicle,
            VEHICLE,
            "regex",
            0.99,
        )

    # ------------------------------------------------------------
    # 9. FIR NUMBER.
    # ------------------------------------------------------------

    for fir_number in extract_fir_numbers(
        normalized_text
    ):

        add_entity(
            entities,
            fir_number,
            FIR_NUMBER,
            "regex",
            0.99,
        )

    # ------------------------------------------------------------
    # 10. CASE ID.
    # ------------------------------------------------------------

    for case_id in extract_case_ids(
        normalized_text
    ):

        add_entity(
            entities,
            case_id,
            CASE_ID,
            "regex",
            0.99,
        )

    # ------------------------------------------------------------
    # 11. MONEY.
    # ------------------------------------------------------------

    for amount in extract_money(
        flat_text
    ):

        add_entity(
            entities,
            amount,
            MONEY,
            "regex",
            0.99,
        )

    # ------------------------------------------------------------
    # 12. ACCOUNT.
    # ------------------------------------------------------------

    for account in extract_accounts(
        normalized_text
    ):

        add_entity(
            entities,
            account,
            ACCOUNT,
            "regex",
            0.99,
        )

    # ------------------------------------------------------------
    # 13. Resolve competing entity classifications.
    # ------------------------------------------------------------

    entities = _resolve_conflicts(
        entities
    )

    # ------------------------------------------------------------
    # 14. Deduplicate.
    # ------------------------------------------------------------

    entities = _deduplicate_entities(
        entities
    )

    # ------------------------------------------------------------
    # 15. Final validation.
    # ------------------------------------------------------------

    entities = _final_validate(
        entities
    )

    # ------------------------------------------------------------
    # 16. Final deduplication.
    # ------------------------------------------------------------

    entities = _deduplicate_entities(
        entities
    )

    # ------------------------------------------------------------
    # 17. Stable ordering.
    # ------------------------------------------------------------

    entities = _sort_entities(
        entities
    )

    logger.info(
        "NER completed: %d entities",
        len(entities),
    )

    return entities


# ================================================================
# TEST DOCUMENT 1
# ================================================================
#
# Important:
# These names are TEST INPUT ONLY.
#
# They are not used by the extraction algorithm.
# ================================================================

TEST_FIR_1 = """
FIRST INFORMATION REPORT

FIR No.: 451/2026
Case ID: TEST-CRIME-2026-001
Police Station: Central Police Station
District: Cuttack
State: Odisha

Date of Registration: 12 September 2026
Date of Incident: 10 September 2026
Time of Incident: 21:30 hrs

Complainant
Name: Inspector Rakesh Verma
Designation: Police Inspector

Incident Location
Cuttack Railway Station Road, near the Old Bus Stand, Cuttack, Odisha.

During investigation, Rahul Sharma was observed communicating with
Priya Nair.

Rahul Sharma was using mobile number 9123456789.
Priya Nair was using mobile number 9876543211.

A white vehicle bearing registration number OD-02-AB-4567
was observed near the incident location.

The investigation identified a company named Sunrise Logistics Pvt. Ltd.
operating from Bhubaneswar.

A bank transfer of ₹1,25,000 was identified.

Persons Mentioned
Rahul Sharma
Priya Nair
Inspector Rakesh Verma

Contact Numbers
9123456789
9876543211

Vehicle
OD-02-AB-4567

Organization
Sunrise Logistics Pvt. Ltd.

Locations
Cuttack Railway Station Road
Cuttack
Bhubaneswar

Status: Open
"""


# ================================================================
# TEST DOCUMENT 2
# ================================================================

TEST_FIR_2 = """
POLICE CASE REPORT

FIR Number: 782/2026
Case ID: CR-88/2024

District: Pune
State: Maharashtra

Incident Location: Pune Central Market Road

The suspect Anil Kapoor contacted Meera Joshi using
mobile number +91 87654 32109.

Another person, Sandeep Rao, was present near Pune Railway Station.

Vehicle registration was MH-12-CD-7890.

Investigators found an account number 123456789012
linked to a financial transaction of INR 87500.

The organization involved was Western Transport Corporation Ltd.

Persons Mentioned
Anil Kapoor
Meera Joshi
Sandeep Rao

Contact Numbers
+91 87654 32109

Vehicle
MH-12-CD-7890

Organization
Western Transport Corporation Ltd.

Locations
Pune
Pune Railway Station
Maharashtra

Status: Under Investigation
"""


# ================================================================
# TEST ASSERTION HELPERS
# ================================================================

def _entity_keys(
    entities: list[dict],
) -> set[tuple[str, str]]:
    """
    Build normalized (type, value) keys.
    """

    keys = set()

    for entity in entities:

        entity_type = get_entity_type(
            entity
        )

        normalized = (
            entity.get(
                "normalized_value"
            )
            or _normalize_entity_value(
                get_entity_text(entity),
                entity_type,
            )
        )

        keys.add(
            (
                entity_type,
                normalized.lower(),
            )
        )

    return keys


def _assert_entity(
    entities: list[dict],
    entity_type: str,
    value: str,
) -> None:
    """
    Assert that an entity exists.
    """

    keys = _entity_keys(
        entities
    )

    normalized = _normalize_entity_value(
        value,
        entity_type,
    )

    expected = (
        entity_type,
        normalized.lower(),
    )

    assert expected in keys, (
        f"Missing expected entity: "
        f"{entity_type}={value!r}"
    )


def _assert_no_entity(
    entities: list[dict],
    entity_type: str,
    value: str,
) -> None:
    """
    Assert that a false-positive entity does not exist.
    """

    keys = _entity_keys(
        entities
    )

    normalized = _normalize_entity_value(
        value,
        entity_type,
    )

    unexpected = (
        entity_type,
        normalized.lower(),
    )

    assert unexpected not in keys, (
        f"Unexpected false-positive entity: "
        f"{entity_type}={value!r}"
    )


# ================================================================
# TEST 1
# ================================================================

def test_fir_1() -> list[dict]:
    """
    Test structured + narrative FIR extraction.
    """

    entities = extract_entities(
        TEST_FIR_1
    )

    # Required PERSON.
    _assert_entity(
        entities,
        PERSON,
        "Rahul Sharma",
    )

    _assert_entity(
        entities,
        PERSON,
        "Priya Nair",
    )

    _assert_entity(
        entities,
        PERSON,
        "Rakesh Verma",
    )

    # Required PHONE.
    _assert_entity(
        entities,
        PHONE,
        "9123456789",
    )

    _assert_entity(
        entities,
        PHONE,
        "9876543211",
    )

    # Required VEHICLE.
    _assert_entity(
        entities,
        VEHICLE,
        "OD-02-AB-4567",
    )

    # Required ORGANIZATION.
    _assert_entity(
        entities,
        ORGANIZATION,
        "Sunrise Logistics Pvt. Ltd.",
    )

    # Required LOCATION.
    _assert_entity(
        entities,
        LOCATION,
        "Cuttack",
    )

    _assert_entity(
        entities,
        LOCATION,
        "Odisha",
    )

    _assert_entity(
        entities,
        LOCATION,
        "Bhubaneswar",
    )

    # Required identifiers.
    _assert_entity(
        entities,
        FIR_NUMBER,
        "451/2026",
    )

    _assert_entity(
        entities,
        CASE_ID,
        "TEST-CRIME-2026-001",
    )

    # Required money.
    _assert_entity(
        entities,
        MONEY,
        "₹1,25,000",
    )

    # Designation must be stripped.
    _assert_no_entity(
        entities,
        PERSON,
        "Inspector",
    )

    _assert_no_entity(
        entities,
        PERSON,
        "Complainant",
    )

    _assert_no_entity(
        entities,
        ORGANIZATION,
        "Time of Incident",
    )

    _assert_no_entity(
        entities,
        ORGANIZATION,
        "Description of Incident",
    )

    _assert_no_entity(
        entities,
        PERSON,
        "Cuttack",
    )

    return entities


# ================================================================
# TEST 2
# ================================================================

def test_fir_2() -> list[dict]:
    """
    Test a different geographic region, organization and narrative
    structure.

    This ensures the extractor is not tuned to Test FIR 1.
    """

    entities = extract_entities(
        TEST_FIR_2
    )

    # PERSON.
    _assert_entity(
        entities,
        PERSON,
        "Anil Kapoor",
    )

    _assert_entity(
        entities,
        PERSON,
        "Meera Joshi",
    )

    _assert_entity(
        entities,
        PERSON,
        "Sandeep Rao",
    )

    # PHONE.
    _assert_entity(
        entities,
        PHONE,
        "8765432109",
    )

    # VEHICLE.
    _assert_entity(
        entities,
        VEHICLE,
        "MH-12-CD-7890",
    )

    # ORGANIZATION.
    _assert_entity(
        entities,
        ORGANIZATION,
        "Western Transport Corporation Ltd.",
    )

    # LOCATION.
    _assert_entity(
        entities,
        LOCATION,
        "Pune",
    )

    _assert_entity(
        entities,
        LOCATION,
        "Maharashtra",
    )

    # ACCOUNT.
    _assert_entity(
        entities,
        ACCOUNT,
        "123456789012",
    )

    # MONEY.
    _assert_entity(
        entities,
        MONEY,
        "INR 87500",
    )

    # FIR.
    _assert_entity(
        entities,
        FIR_NUMBER,
        "782/2026",
    )

    # CASE.
    _assert_entity(
        entities,
        CASE_ID,
        "CR-88/2024",
    )

    # False-positive protection.
    _assert_no_entity(
        entities,
        PERSON,
        "Police Case Report",
    )

    _assert_no_entity(
        entities,
        PERSON,
        "District",
    )

    _assert_no_entity(
        entities,
        ORGANIZATION,
        "Pune",
    )

    return entities


# ================================================================
# TEST OUTPUT
# ================================================================

def _print_test_results(
    name: str,
    entities: list[dict],
) -> None:
    """
    Print readable test output.
    """

    print()
    print(
        "-" * 64
    )

    print(
        name
    )

    print(
        "-" * 64
    )

    for entity in entities:

        print(
            f"{get_entity_type(entity):<15} "
            f"{get_entity_text(entity):<40} "
            f"{entity.get('source', ''):<12} "
            f"{entity.get('confidence', '')}"
        )

    print(
        "-" * 64
    )


# ================================================================
# COMPLETE SELF-TEST
# ================================================================

def run_self_tests() -> bool:
    """
    Run BOTH independent FIR tests.

    Test 1:
        Odisha / Cuttack-style FIR.

    Test 2:
        Maharashtra / Pune-style FIR.

    The test suite checks:
        - PERSON
        - PHONE
        - VEHICLE
        - ORGANIZATION
        - LOCATION
        - ACCOUNT
        - FIR_NUMBER
        - CASE_ID
        - MONEY
        - designation stripping
        - false-positive filtering
    """

    print()
    print(
        "=" * 64
    )

    print(
        "SIH26189 — IDEA 1 NER SELF-TEST"
    )

    print(
        "=" * 64
    )

    print()
    print(
        f"spaCy model: {MODEL_NAME}"
    )

    print(
        f"Gazetteer entries: {len(GAZETTEER)}"
    )

    # ------------------------------------------------------------
    # Test 1
    # ------------------------------------------------------------

    print()
    print(
        "Running TEST 1..."
    )

    entities_1 = test_fir_1()

    _print_test_results(
        "TEST 1 PASSED",
        entities_1,
    )

    # ------------------------------------------------------------
    # Test 2
    # ------------------------------------------------------------

    print(
        "Running TEST 2..."
    )

    entities_2 = test_fir_2()

    _print_test_results(
        "TEST 2 PASSED",
        entities_2,
    )

    # ------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------

    print()
    print(
        "=" * 64
    )

    print(
        "ALL NER SELF-TESTS PASSED"
    )

    print(
        "=" * 64
    )

    print()
    print(
        "The extractor is ready for integration testing."
    )

    print()

    return True


# ================================================================
# COMMAND-LINE ENTRY POINT
# ================================================================

if __name__ == "__main__":
    run_self_tests()