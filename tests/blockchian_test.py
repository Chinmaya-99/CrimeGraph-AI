from data_base.database import SessionLocal
from models.audit import AuditLedger
from services.blockchain_service import (
    record_test_event,
    verify_block,
)


def verify_test_segment(db, ledger_ids):
    """
    Verify only the blocks created by this test.

    The first test block is anchored to whatever historical block
    existed before the test. We intentionally do not validate that
    historical block.

    Subsequent test blocks must link to the previous test block.
    """

    blocks = (
        db.query(AuditLedger)
        .filter(AuditLedger.ledger_id.in_(ledger_ids))
        .order_by(AuditLedger.ledger_id.asc())
        .all()
    )

    if len(blocks) != len(ledger_ids):
        print("ERROR: Could not retrieve all test blocks.")
        return False

    valid = True

    for index, block in enumerate(blocks):
        result = verify_block(block)

        print(f"\nBLOCK #{block.ledger_id}")
        print(f"  record_hash_valid : {result['record_hash_valid']}")
        print(f"  chain_hash_valid  : {result['chain_hash_valid']}")

        if not result["record_hash_valid"]:
            valid = False

        if not result["chain_hash_valid"]:
            valid = False

        # Only validate internal linkage between blocks created
        # during this test. The first block may point to old history.
        if index > 0:
            previous_block = blocks[index - 1]

            previous_link_valid = (
                block.previous_hash == previous_block.chain_hash
            )

            print(
                f"  previous_link_valid : {previous_link_valid}"
            )

            if not previous_link_valid:
                valid = False

    return valid


def main():
    db = SessionLocal()

    created_ids = []

    try:
        print("=" * 70)
        print("BLOCKCHAIN TEST")
        print("=" * 70)

        # ------------------------------------------------------------
        # 1. CREATE TEST BLOCKS
        # ------------------------------------------------------------

        print("\n[1] Creating test blocks...")

        block_1 = record_test_event(
            db,
            "Blockchain test block 1"
        )

        block_2 = record_test_event(
            db,
            "Blockchain test block 2"
        )

        block_3 = record_test_event(
            db,
            "Blockchain test block 3"
        )

        created_ids = [
    block_1["ledger_id"],
    block_2["ledger_id"],
    block_3["ledger_id"],
]
        db.commit()

        print(f"Created blocks: {created_ids}")

        # ------------------------------------------------------------
        # 2. READ BACK BLOCKS
        # ------------------------------------------------------------

        print("\n[2] Reading test blocks back from database...")

        blocks = (
            db.query(AuditLedger)
            .filter(AuditLedger.ledger_id.in_(created_ids))
            .order_by(AuditLedger.ledger_id.asc())
            .all()
        )

        for block in blocks:
            print("\n----------------------------------------")
            print(f"LEDGER ID     : {block.ledger_id}")
            print(f"EVENT TYPE    : {block.event_type}")
            print(f"RECORD HASH   : {block.record_hash}")
            print(f"PREVIOUS HASH : {block.previous_hash}")
            print(f"CHAIN HASH    : {block.chain_hash}")
            print(f"METADATA      : {block.metadata_}")

        # ------------------------------------------------------------
        # 3. VERIFY CLEAN TEST SEGMENT
        # ------------------------------------------------------------

        print("\n[3] Verifying newly created blockchain segment...")

        valid = verify_test_segment(
            db,
            created_ids
        )

        print("\n========================================")
        print(f"TEST SEGMENT VALID: {valid}")
        print("========================================")

        if not valid:
            raise RuntimeError(
                "Newly created blockchain test segment is invalid."
            )

        # ------------------------------------------------------------
        # 4. TAMPER WITH ONE BLOCK
        # ------------------------------------------------------------

        print("\n[4] Simulating database tampering...")

        tampered_block = (
            db.query(AuditLedger)
            .filter(
                AuditLedger.ledger_id == created_ids[1]
            )
            .one()
        )

        original_metadata = dict(
            tampered_block.metadata_
            or {}
        )

        tampered_metadata = dict(original_metadata)
        tampered_metadata["tampered"] = True

        tampered_block.metadata_ = tampered_metadata

        # IMPORTANT:
        # We intentionally do NOT update record_hash or chain_hash.
        #
        # This simulates someone changing database content directly
        # without possessing the correct blockchain hashes.

        db.commit()

        print(
            f"Tampered block: {tampered_block.ledger_id}"
        )

        # ------------------------------------------------------------
        # 5. VERIFY TAMPER DETECTION
        # ------------------------------------------------------------

        print("\n[5] Verifying tampered blockchain segment...")

        tampered_valid = verify_test_segment(
            db,
            created_ids
        )

        print("\n========================================")
        print(
            f"TAMPERED SEGMENT VALID: {tampered_valid}"
        )
        print("========================================")

        if tampered_valid:
            raise RuntimeError(
                "Tampering was NOT detected."
            )

        print("\nSUCCESS:")
        print(
            "Blockchain test passed. "
            "Valid blocks were accepted and database tampering "
            "was detected."
        )

    finally:
        # ------------------------------------------------------------
        # 6. CLEANUP ONLY TEST BLOCKS
        # ------------------------------------------------------------

        print("\n[6] Cleaning up test blocks...")

        if created_ids:
            (
                db.query(AuditLedger)
                .filter(
                    AuditLedger.ledger_id.in_(created_ids)
                )
                .delete(
                    synchronize_session=False
                )
            )

            db.commit()

            print(
                f"Deleted test blocks: {created_ids}"
            )

        db.close()


if __name__ == "__main__":
    main()