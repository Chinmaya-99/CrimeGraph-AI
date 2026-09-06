from sqlalchemy import text

from data_base.database import SessionLocal
from services.cross_lookup import run_cross_lookup
from services.new_ner import extract_entities


TEXT = """
FIR No. 123/2026

Complainant: Arjun Mehta
Accused: Ravi Das
Witness: Vikram Singh

Incident occurred at Cuttack Railway Station, Odisha.

Vehicle involved: OD05AB1234

Contact number: 9876543210

Organization: Eastern Logistics Pvt. Ltd.
"""
def print_raw_lookup_details(result):
    print("\n========== MATCH DETAILS ==========\n")

    for hit in result.entity_hits:
        print(f"{hit.entity_type}: {hit.entity_value}")

        if hit.contact_hits:
            print(f"  CONTACT: {len(hit.contact_hits)} records")

        if hit.bank_hits:
            print(f"  BANK: {len(hit.bank_hits)} records")

        if hit.crime_hits:
            print(f"  CRIME: {len(hit.crime_hits)} records")

        if hit.surveillance_hits:
            print(
                f"  SURVEILLANCE: "
                f"{len(hit.surveillance_hits)} records"
            )

        if hit.social_hits:
            print(
                f"  SOCIAL: "
                f"{len(hit.social_hits)} records"
            )

        if hit.fir_hits:
            print(
                f"  OTHER FIR: "
                f"{len(hit.fir_hits)} records"
            )

        print()
def main():
    db = SessionLocal()

    try:
        entities = extract_entities(TEXT)

        print("\n========== NER RESULT ==========\n")

        for entity in entities:
            print(
                f"TYPE   : {entity.get('type')}\n"
                f"TEXT   : {entity.get('text')}\n"
                f"SOURCE : {entity.get('source')}\n"
                f"-------------------------------"
            )

        print(
            f"\nTotal entities: {len(entities)}"
        )


        # Use an existing FIR record so that
        # extracted_entities.fir_id satisfies
        # the foreign-key constraint.
        test_fir_id = 2

        result = run_cross_lookup(
            db=db,
            fir_id=test_fir_id,
            entities=entities,
        )

        print(
            "\n========== CROSS LOOKUP RESULT ==========\n"
        )

        print(
            f"FIR ID          : {result.fir_id}"
        )
        print(
            f"Total entities  : {result.total_entities}"
        )

        for hit in result.entity_hits:
            print(
                "\n-----------------------------------------"
            )

            print(
                f"ENTITY TYPE     : {hit.entity_type}"
            )
            print(
                f"ENTITY VALUE    : {hit.entity_value}"
            )
            print(
                f"DB HIT COUNT    : {hit.db_hit_count}"
            )
            print(
                f"ENTITY SCORE    : {hit.entity_score:.4f}"
            )

            print(
                f"CONTACT HITS    : "
                f"{len(hit.contact_hits)}"
            )
            print(
                f"BANK HITS       : "
                f"{len(hit.bank_hits)}"
            )
            print(
                f"CRIME HITS      : "
                f"{len(hit.crime_hits)}"
            )
            print(
                f"SURVEILLANCE    : "
                f"{len(hit.surveillance_hits)}"
            )
            print(
                f"SOCIAL HITS     : "
                f"{len(hit.social_hits)}"
            )
            print(
                f"OTHER FIR HITS  : "
                f"{len(hit.fir_hits)}"
            )

        print("==raw lookup details==")
        print_raw_lookup_details(result)
        # This test should not permanently modify
        # extracted_entities or any other database data.
        db.rollback()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()