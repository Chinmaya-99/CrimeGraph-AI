from services.new_ner import extract_entities


TEXT = """
FIR No. 123/2026

Complainant: Anil Das
Accused: Rahul Kumar
Witness: Arjun Singh

Incident occurred at Cuttack Railway Station, Odisha.

Vehicle involved: OD-05-AB-1234

Contact number: 9876543210

Organization: Eastern Logistics Pvt. Ltd.
"""


def main():
    entities = extract_entities(TEXT)

    print("\n========== NER RESULT ==========\n")

    for entity in entities:
        print(
            f"TYPE   : {entity.get('type')}\n"
            f"TEXT   : {entity.get('text')}\n"
            f"SOURCE : {entity.get('source')}\n"
            f"-------------------------------"
        )

    print(f"\nTotal entities: {len(entities)}")


if __name__ == "__main__":
    main()