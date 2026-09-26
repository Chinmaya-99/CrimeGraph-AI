"""
Blockchain / Tamper-Evident Audit Service
=========================================

This service implements the blockchain-style hash chain using the
existing `audit_ledger` table.

Architecture:

    event
      ↓
    record_hash
      ↓
    previous_hash
      ↓
    chain_hash

The PostgreSQL database remains the source of truth.

IMPORTANT:
- No new database is created.
- No new table is required.
- No existing table is modified.
- This service uses the existing `audit_ledger` model.
- The service does NOT commit transactions.
- The caller owns commit / rollback.

Current chain model:

    GENESIS
       ↓
    Block 1
       ↓
    Block 2
       ↓
    Block 3
       ↓
      ...

Each block contains the hash of its own data and the hash of the
previous block.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from models.audit import AuditLedger


# ================================================================
# CONSTANTS
# ================================================================

GENESIS_HASH = "GENESIS"

CHAIN_LOCK_KEY = "audit_ledger_chain"


# ================================================================
# EXCEPTIONS
# ================================================================

class BlockchainServiceError(Exception):
    """Base exception for blockchain service errors."""


class BlockchainVerificationError(BlockchainServiceError):
    """Raised when blockchain integrity verification fails."""


# ================================================================
# CANONICAL JSON
# ================================================================

def canonical_json(data: Any) -> str:
    """
    Convert data into deterministic JSON.

    Deterministic serialization is required because the same logical
    event must always produce the same SHA-256 hash.
    """

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    )


# ================================================================
# SHA-256
# ================================================================

def sha256_text(value: str) -> str:
    """
    Calculate SHA-256 hash for UTF-8 text.
    """

    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def calculate_data_hash(data: Any) -> str:
    """
    Calculate SHA-256 hash for structured data.
    """

    return sha256_text(
        canonical_json(data)
    )


# ================================================================
# RECORD HASH
# ================================================================

def build_record_payload(
    event_type: str,
    target_table: str | None,
    target_record_id: int | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Build the exact deterministic payload used for record_hash.

    NOTE:
    created_at is intentionally NOT included.

    PostgreSQL generates created_at using CURRENT_TIMESTAMP, so using
    it inside the hash before insertion would make deterministic
    verification unnecessarily difficult.

    The cryptographic chain instead covers the actual event content.
    """

    return {
        "event_type": event_type,
        "target_table": target_table,
        "target_record_id": target_record_id,
        "metadata": metadata,
    }


def calculate_record_hash(
    event_type: str,
    target_table: str | None,
    target_record_id: int | None,
    metadata: dict[str, Any],
) -> str:
    """
    Calculate the SHA-256 hash of one ledger event.
    """

    payload = build_record_payload(
        event_type=event_type,
        target_table=target_table,
        target_record_id=target_record_id,
        metadata=metadata,
    )

    return calculate_data_hash(payload)


# ================================================================
# CHAIN HASH
# ================================================================

def calculate_chain_hash(
    record_hash: str,
    previous_hash: str,
) -> str:
    """
    Calculate the hash linking this block to the previous block.

        chain_hash = SHA256(record_hash + previous_hash)
    """

    return sha256_text(
        record_hash + previous_hash
    )


# ================================================================
# CHAIN LOCK
# ================================================================

def lock_chain(db: Session) -> None:
    """
    Acquire a PostgreSQL transaction-level advisory lock.

    This prevents concurrent requests from doing:

        Request A → previous_hash = X
        Request B → previous_hash = X

    and creating two competing next blocks.

    The lock is automatically released when the transaction ends.
    """

    db.execute(
        text(
            """
            SELECT pg_advisory_xact_lock(
                hashtext(:lock_key)
            )
            """
        ),
        {
            "lock_key": CHAIN_LOCK_KEY,
        },
    )


# ================================================================
# GET LATEST BLOCK
# ================================================================

def get_latest_block(
    db: Session,
) -> AuditLedger | None:
    """
    Return the latest block from the audit ledger.

    Returns:
        AuditLedger | None
    """

    return (
        db.query(AuditLedger)
        .order_by(AuditLedger.ledger_id.desc())
        .first()
    )


# ================================================================
# GET BLOCK
# ================================================================

def get_block(
    db: Session,
    ledger_id: int,
) -> AuditLedger | None:
    """
    Fetch one ledger block by ID.
    """

    return (
        db.query(AuditLedger)
        .filter(
            AuditLedger.ledger_id == ledger_id
        )
        .first()
    )


# ================================================================
# RECORD EVENT
# ================================================================

def record_event(
    db: Session,
    event_type: str,
    target_table: str | None = None,
    target_record_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    actor_id: int | None = None,
    actor_role: str = "system",
) -> dict[str, Any]:
    """
    Append one event to the blockchain ledger.

    IMPORTANT:
    This function does NOT commit.

    The caller controls the transaction.

    Example:

        event = record_event(
            db=db,
            event_type="TEST_EVENT",
            target_table="fir_records",
            target_record_id=123,
            metadata={
                "message": "Blockchain test"
            },
            actor_id=1,
            actor_role="admin",
        )

        db.commit()
    """

    if not event_type:
        raise BlockchainServiceError(
            "event_type is required."
        )

    if metadata is None:
        metadata = {}

    # ------------------------------------------------------------
    # Lock the blockchain chain.
    # ------------------------------------------------------------

    lock_chain(db)

    # ------------------------------------------------------------
    # Find previous block.
    # ------------------------------------------------------------

    previous_block = get_latest_block(db)

    if previous_block is None:
        previous_hash = GENESIS_HASH
    else:
        previous_hash = previous_block.chain_hash

    # ------------------------------------------------------------
    # Calculate record hash.
    # ------------------------------------------------------------

    record_hash = calculate_record_hash(
        event_type=event_type,
        target_table=target_table,
        target_record_id=target_record_id,
        metadata=metadata,
    )

    # ------------------------------------------------------------
    # Calculate chain hash.
    # ------------------------------------------------------------

    chain_hash = calculate_chain_hash(
        record_hash=record_hash,
        previous_hash=previous_hash,
    )

    # ------------------------------------------------------------
    # Create ORM ledger record.
    # ------------------------------------------------------------

    ledger_entry = AuditLedger(
        event_type=event_type,
        actor_id=actor_id,
        actor_role=actor_role,
        target_table=target_table,
        target_record_id=target_record_id,
        record_hash=record_hash,
        previous_hash=previous_hash,
        chain_hash=chain_hash,
        metadata_=metadata,
    )

    db.add(ledger_entry)

    # ------------------------------------------------------------
    # Flush.
    #
    # This generates ledger_id and server-generated created_at
    # without committing the transaction.
    # ------------------------------------------------------------

    db.flush()

    return ledger_entry.to_dict()


# ================================================================
# FIR EVENT
# ================================================================

def record_fir_event(
    db: Session,
    fir_id: int,
    event_type: str,
    metadata: dict[str, Any] | None = None,
    actor_id: int | None = None,
    actor_role: str = "system",
) -> dict[str, Any]:
    """
    Convenience helper for FIR-related blockchain events.
    """

    return record_event(
        db=db,
        event_type=event_type,
        target_table="fir_records",
        target_record_id=fir_id,
        metadata=metadata or {},
        actor_id=actor_id,
        actor_role=actor_role,
    )


# ================================================================
# GET COMPLETE CHAIN
# ================================================================

def get_chain(
    db: Session,
) -> list[dict[str, Any]]:
    """
    Return the complete blockchain in chronological order.
    """

    blocks = (
        db.query(AuditLedger)
        .order_by(AuditLedger.ledger_id.asc())
        .all()
    )

    return [
        block.to_dict()
        for block in blocks
    ]


# ================================================================
# GET FIR EVENTS
# ================================================================

def get_fir_chain(
    db: Session,
    fir_id: int,
) -> list[dict[str, Any]]:
    """
    Return all blockchain events associated with a specific FIR.

    This is a filtered view of the global blockchain.
    """

    blocks = (
        db.query(AuditLedger)
        .filter(
            AuditLedger.target_table == "fir_records",
            AuditLedger.target_record_id == fir_id,
        )
        .order_by(AuditLedger.ledger_id.asc())
        .all()
    )

    return [
        block.to_dict()
        for block in blocks
    ]


# ================================================================
# VERIFY ONE BLOCK
# ================================================================

def verify_block(
    block: AuditLedger,
) -> dict[str, Any]:
    """
    Verify the cryptographic integrity of one block.

    Checks:

        stored record_hash
              vs
        recalculated record_hash

    and:

        stored chain_hash
              vs
        SHA256(record_hash + previous_hash)
    """

    metadata = block.metadata_ or {}

    calculated_record_hash = calculate_record_hash(
        event_type=block.event_type,
        target_table=block.target_table,
        target_record_id=block.target_record_id,
        metadata=metadata,
    )

    calculated_chain_hash = calculate_chain_hash(
        record_hash=calculated_record_hash,
        previous_hash=block.previous_hash,
    )

    record_hash_valid = (
        calculated_record_hash
        == block.record_hash
    )

    chain_hash_valid = (
        calculated_chain_hash
        == block.chain_hash
    )

    return {
        "ledger_id": block.ledger_id,
        "event_type": block.event_type,
        "record_hash_valid": record_hash_valid,
        "chain_hash_valid": chain_hash_valid,
        "valid": (
            record_hash_valid
            and chain_hash_valid
        ),
        "stored_record_hash": block.record_hash,
        "calculated_record_hash": calculated_record_hash,
        "stored_chain_hash": block.chain_hash,
        "calculated_chain_hash": calculated_chain_hash,
        "previous_hash": block.previous_hash,
    }


# ================================================================
# VERIFY COMPLETE CHAIN
# ================================================================

def verify_chain(
    db: Session,
) -> dict[str, Any]:
    """
    Verify the complete blockchain.

    Verification includes:

    1. Genesis linkage.
    2. Previous-hash linkage.
    3. Individual record hashes.
    4. Individual chain hashes.
    """

    blocks = (
        db.query(AuditLedger)
        .order_by(AuditLedger.ledger_id.asc())
        .all()
    )

    # ------------------------------------------------------------
    # Empty chain.
    # ------------------------------------------------------------

    if not blocks:

        return {
            "valid": True,
            "total_blocks": 0,
            "verified_blocks": 0,
            "failed_blocks": [],
            "message": "Blockchain ledger is empty.",
        }

    failed_blocks: list[dict[str, Any]] = []

    expected_previous_hash = GENESIS_HASH

    # ------------------------------------------------------------
    # Walk through the chain.
    # ------------------------------------------------------------

    for block in blocks:

        # --------------------------------------------------------
        # Check previous-hash linkage.
        # --------------------------------------------------------

        previous_hash_valid = (
            block.previous_hash
            == expected_previous_hash
        )

        # --------------------------------------------------------
        # Check block's own cryptographic hashes.
        # --------------------------------------------------------

        block_result = verify_block(
            block
        )

        block_valid = (
            previous_hash_valid
            and block_result["valid"]
        )

        if not block_valid:

            failed_blocks.append(
                {
                    "ledger_id": block.ledger_id,
                    "event_type": block.event_type,
                    "previous_hash_valid": (
                        previous_hash_valid
                    ),
                    "record_hash_valid": (
                        block_result[
                            "record_hash_valid"
                        ]
                    ),
                    "chain_hash_valid": (
                        block_result[
                            "chain_hash_valid"
                        ]
                    ),
                }
            )

        # --------------------------------------------------------
        # The current block becomes the expected previous block
        # for the next iteration.
        # --------------------------------------------------------

        expected_previous_hash = block.chain_hash

    # ------------------------------------------------------------
    # Final result.
    # ------------------------------------------------------------

    valid = len(failed_blocks) == 0

    return {
        "valid": valid,
        "total_blocks": len(blocks),
        "verified_blocks": (
            len(blocks) - len(failed_blocks)
        ),
        "failed_blocks": failed_blocks,
        "message": (
            "Blockchain integrity verified."
            if valid
            else "Blockchain integrity verification failed."
        ),
    }


# ================================================================
# VERIFY FIR
# ================================================================

def verify_fir(
    db: Session,
    fir_id: int,
) -> dict[str, Any]:
    """
    Verify the complete blockchain and return the events associated
    with one FIR.
    """

    blockchain_result = verify_chain(
        db
    )

    fir_events = get_fir_chain(
        db=db,
        fir_id=fir_id,
    )

    return {
        "fir_id": fir_id,
        "blockchain_valid": (
            blockchain_result["valid"]
        ),
        "total_ledger_blocks": (
            blockchain_result["total_blocks"]
        ),
        "fir_event_count": len(fir_events),
        "events": fir_events,
        "failed_blocks": (
            blockchain_result["failed_blocks"]
        ),
    }


# ================================================================
# VERIFY SOURCE HASH
# ================================================================

def verify_source_hash(
    db: Session,
    fir_id: int,
    current_source_hash: str,
) -> dict[str, Any]:
    """
    Verify that a current PDF SHA-256 matches the source hash stored
    against the FIR.

    This checks the evidence itself against the hash recorded in
    PostgreSQL.

    The blockchain event containing that source hash can then provide
    the tamper-evident provenance trail.
    """

    from models.fir import FIRRecord

    fir = (
        db.query(FIRRecord)
        .filter(
            FIRRecord.fir_id == fir_id
        )
        .first()
    )

    if fir is None:

        raise BlockchainServiceError(
            f"FIR {fir_id} was not found."
        )

    stored_hash = fir.source_hash

    matches = (
        stored_hash is not None
        and stored_hash.lower()
        == current_source_hash.lower()
    )

    return {
        "fir_id": fir_id,
        "source_file": fir.source_file,
        "stored_source_hash": stored_hash,
        "current_source_hash": current_source_hash,
        "hash_matches": matches,
        "integrity_status": (
            "VERIFIED"
            if matches
            else "MISMATCH"
        ),
    }


# ================================================================
# VERIFY BLOCKCHAIN + SOURCE
# ================================================================

def verify_fir_integrity(
    db: Session,
    fir_id: int,
    current_source_hash: str | None = None,
) -> dict[str, Any]:
    """
    Combined integrity verification.

    Checks:

        1. Blockchain chain integrity.
        2. FIR provenance events.
        3. Optional current PDF hash.

    If current_source_hash is not supplied, only the blockchain
    provenance chain is verified.
    """

    result = verify_fir(
        db=db,
        fir_id=fir_id,
    )

    result["source_integrity"] = None

    if current_source_hash:

        result["source_integrity"] = (
            verify_source_hash(
                db=db,
                fir_id=fir_id,
                current_source_hash=current_source_hash,
            )
        )

    return result


# ================================================================
# TEST EVENT
# ================================================================

def record_test_event(
    db: Session,
    message: str = "Blockchain test event",
) -> dict[str, Any]:
    """
    Convenience helper for development/testing.

    This creates a harmless TEST_BLOCKCHAIN event.

    It does NOT modify FIR data.
    """

    return record_event(
        db=db,
        event_type="TEST_BLOCKCHAIN",
        target_table="system",
        target_record_id=None,
        metadata={
            "message": message,
            "test": True,
        },
        actor_id=None,
        actor_role="system",
    )