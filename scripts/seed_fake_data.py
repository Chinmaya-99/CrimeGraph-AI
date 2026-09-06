# scripts/seed_fake_data.py

"""
SIH26189
============================================================
Fake / Demo Data Seeder

Creates:
    20 FIR records
    20 Contact / CDR records
    20 Bank records
    20 Social-media records
    20 Previous-crime records
    20 Surveillance records

Total:
    120 source records

IMPORTANT:
    All data in this file is fictional and intended only for
    development, testing, demonstrations and hackathon use.

The dataset is intentionally interconnected so that the
cross-lookup service can discover relationships between:

    PERSON
    PHONE
    VEHICLE
    LOCATION
    ORGANIZATION
    ACCOUNT

Run from the backend/project environment:

    python scripts/seed_fake_data.py
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

# ------------------------------------------------------------
# Make backend root importable when running:
#
#     python scripts/seed_fake_data.py
# ------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from sqlalchemy.orm import Session

from data_base.database import SessionLocal, init_db

from models.fir import FIRRecord
from models.contact import ContactRecord
from models.bank import BankRecord
from models.social import SocialMediaRecord
from models.crime import PreviousCrimeRecord
from models.surveillance import SurveillanceRecord


# ================================================================
# FICTIONAL PEOPLE
# ================================================================

PEOPLE = [
    {
        "name": "Arjun Mehta",
        "phone": "9876543210",
        "vehicle": "OD-05-AB-1234",
        "location": "Cuttack",
    },
    {
        "name": "Ravi Das",
        "phone": "9876543211",
        "vehicle": "OD-02-CD-5678",
        "location": "Bhubaneswar",
    },
    {
        "name": "Vikram Singh",
        "phone": "9876543212",
        "vehicle": "OD-33-EF-9012",
        "location": "Puri",
    },
    {
        "name": "Suresh Patel",
        "phone": "9876543213",
        "vehicle": "OD-14-GH-3456",
        "location": "Rourkela",
    },
    {
        "name": "Neha Sharma",
        "phone": "9876543214",
        "vehicle": "OD-05-JK-7890",
        "location": "Cuttack",
    },
    {
        "name": "Priya Nanda",
        "phone": "9876543215",
        "vehicle": "OD-02-LM-2345",
        "location": "Bhubaneswar",
    },
    {
        "name": "Amit Kumar",
        "phone": "9876543216",
        "vehicle": "OD-33-NP-6789",
        "location": "Puri",
    },
    {
        "name": "Rohit Jena",
        "phone": "9876543217",
        "vehicle": "OD-14-QR-0123",
        "location": "Rourkela",
    },
    {
        "name": "Manoj Behera",
        "phone": "9876543218",
        "vehicle": "OD-05-ST-4567",
        "location": "Cuttack",
    },
    {
        "name": "Karan Shah",
        "phone": "9876543219",
        "vehicle": "OD-02-UV-8901",
        "location": "Bhubaneswar",
    },
]


# ================================================================
# FICTIONAL ORGANIZATIONS
# ================================================================

ORGANIZATIONS = [
    "Eastern Logistics",
    "Coastal Traders",
    "Odisha Transport Network",
    "Blue River Exports",
]


# ================================================================
# LOCATIONS
# ================================================================

LOCATIONS = [
    "Cuttack",
    "Bhubaneswar",
    "Puri",
    "Rourkela",
]


# ================================================================
# BASE DATE
# ================================================================

BASE_DATE = datetime(2026, 1, 10, 10, 30, 0)


# ================================================================
# HELPERS
# ================================================================

def fake_date(days: int = 0, hours: int = 0) -> datetime:
    """
    Generate deterministic timestamps for the fake dataset.
    """
    return BASE_DATE + timedelta(
        days=days,
        hours=hours,
    )


def source_hash(name: str) -> str:
    """
    Generate a deterministic SHA-256 value.

    This is only a fake provenance hash for demo data.
    It does NOT represent a real uploaded document.
    """
    return hashlib.sha256(
        f"FAKE-SIH-DATA::{name}".encode("utf-8")
    ).hexdigest()


def get_person(index: int) -> dict:
    """
    Return a person using cyclic indexing.
    """
    return PEOPLE[index % len(PEOPLE)]


def get_next_person(index: int) -> dict:
    """
    Return the next person in the fictional network.
    """
    return PEOPLE[(index + 1) % len(PEOPLE)]


def get_person_by_name(name: str) -> dict:
    """
    Find a person by exact fictional name.
    """
    for person in PEOPLE:
        if person["name"] == name:
            return person

    raise ValueError(f"Unknown fake person: {name}")


def add_records(db: Session, records: list) -> None:
    """
    Add a list of SQLAlchemy records to the current session.
    """
    db.add_all(records)


# ================================================================
# 1. FIR RECORDS
# ================================================================

def create_fir_records() -> list[FIRRecord]:
    """
    Create 20 interconnected fictional FIR records.
    """

    fir_data = [
        {
            "case_id": "SIH-CRIME-2026-0001",
            "fir_number": "127/2026",
            "persons": ["Arjun Mehta", "Ravi Das"],
            "vehicles": ["OD-05-AB-1234"],
            "phones": ["9876543210", "9876543211"],
            "orgs": ["Eastern Logistics"],
            "location": "Cuttack",
            "description": (
                "A suspicious meeting between Arjun Mehta and Ravi Das "
                "was reported near a commercial warehouse in Cuttack."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0002",
            "fir_number": "143/2026",
            "persons": ["Ravi Das", "Vikram Singh"],
            "vehicles": ["OD-02-CD-5678"],
            "phones": ["9876543211", "9876543212"],
            "orgs": ["Coastal Traders"],
            "location": "Bhubaneswar",
            "description": (
                "Ravi Das was observed communicating with Vikram Singh "
                "during a suspected financial transaction."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0003",
            "fir_number": "151/2026",
            "persons": ["Vikram Singh", "Suresh Patel"],
            "vehicles": ["OD-33-EF-9012"],
            "phones": ["9876543212", "9876543213"],
            "orgs": ["Blue River Exports"],
            "location": "Puri",
            "description": (
                "Authorities received information regarding a meeting "
                "between Vikram Singh and Suresh Patel in Puri."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0004",
            "fir_number": "162/2026",
            "persons": ["Suresh Patel", "Neha Sharma"],
            "vehicles": ["OD-14-GH-3456"],
            "phones": ["9876543213", "9876543214"],
            "orgs": ["Odisha Transport Network"],
            "location": "Rourkela",
            "description": (
                "A vehicle registered to Suresh Patel was linked to "
                "an investigation involving Neha Sharma."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0005",
            "fir_number": "174/2026",
            "persons": ["Neha Sharma", "Priya Nanda"],
            "vehicles": ["OD-05-JK-7890"],
            "phones": ["9876543214", "9876543215"],
            "orgs": ["Eastern Logistics"],
            "location": "Cuttack",
            "description": (
                "Neha Sharma and Priya Nanda were reported at the same "
                "location during an investigation."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0006",
            "fir_number": "181/2026",
            "persons": ["Priya Nanda", "Amit Kumar"],
            "vehicles": ["OD-02-LM-2345"],
            "phones": ["9876543215", "9876543216"],
            "orgs": ["Coastal Traders"],
            "location": "Bhubaneswar",
            "description": (
                "Investigators identified communication between Priya "
                "Nanda and Amit Kumar."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0007",
            "fir_number": "193/2026",
            "persons": ["Amit Kumar", "Rohit Jena"],
            "vehicles": ["OD-33-NP-6789"],
            "phones": ["9876543216", "9876543217"],
            "orgs": ["Blue River Exports"],
            "location": "Puri",
            "description": (
                "A suspected exchange involving Amit Kumar and Rohit "
                "Jena was reported in Puri."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0008",
            "fir_number": "204/2026",
            "persons": ["Rohit Jena", "Manoj Behera"],
            "vehicles": ["OD-14-QR-0123"],
            "phones": ["9876543217", "9876543218"],
            "orgs": ["Odisha Transport Network"],
            "location": "Rourkela",
            "description": (
                "Rohit Jena and Manoj Behera were connected through "
                "a vehicle movement reported in Rourkela."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0009",
            "fir_number": "218/2026",
            "persons": ["Manoj Behera", "Karan Shah"],
            "vehicles": ["OD-05-ST-4567"],
            "phones": ["9876543218", "9876543219"],
            "orgs": ["Eastern Logistics"],
            "location": "Cuttack",
            "description": (
                "Manoj Behera was reported meeting Karan Shah near "
                "an Eastern Logistics facility."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0010",
            "fir_number": "229/2026",
            "persons": ["Karan Shah", "Arjun Mehta"],
            "vehicles": ["OD-02-UV-8901"],
            "phones": ["9876543219", "9876543210"],
            "orgs": ["Coastal Traders"],
            "location": "Bhubaneswar",
            "description": (
                "Karan Shah and Arjun Mehta were identified in a "
                "suspected coordination meeting."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0011",
            "fir_number": "237/2026",
            "persons": ["Arjun Mehta", "Vikram Singh"],
            "vehicles": ["OD-05-AB-1234"],
            "phones": ["9876543210", "9876543212"],
            "orgs": ["Blue River Exports"],
            "location": "Puri",
            "description": (
                "Arjun Mehta and Vikram Singh were linked to a "
                "transaction under investigation."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0012",
            "fir_number": "245/2026",
            "persons": ["Ravi Das", "Suresh Patel"],
            "vehicles": ["OD-02-CD-5678"],
            "phones": ["9876543211", "9876543213"],
            "orgs": ["Odisha Transport Network"],
            "location": "Rourkela",
            "description": (
                "A transport-related investigation identified Ravi "
                "Das and Suresh Patel as persons of interest."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0013",
            "fir_number": "256/2026",
            "persons": ["Neha Sharma", "Amit Kumar"],
            "vehicles": ["OD-05-JK-7890"],
            "phones": ["9876543214", "9876543216"],
            "orgs": ["Eastern Logistics"],
            "location": "Cuttack",
            "description": (
                "Neha Sharma and Amit Kumar appeared in records "
                "related to a suspicious shipment."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0014",
            "fir_number": "267/2026",
            "persons": ["Priya Nanda", "Rohit Jena"],
            "vehicles": ["OD-02-LM-2345"],
            "phones": ["9876543215", "9876543217"],
            "orgs": ["Coastal Traders"],
            "location": "Bhubaneswar",
            "description": (
                "Investigators found communication between Priya "
                "Nanda and Rohit Jena."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0015",
            "fir_number": "278/2026",
            "persons": ["Manoj Behera", "Vikram Singh"],
            "vehicles": ["OD-05-ST-4567"],
            "phones": ["9876543218", "9876543212"],
            "orgs": ["Blue River Exports"],
            "location": "Puri",
            "description": (
                "Manoj Behera and Vikram Singh were associated with "
                "a suspicious shipment in Puri."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0016",
            "fir_number": "289/2026",
            "persons": ["Karan Shah", "Suresh Patel"],
            "vehicles": ["OD-02-UV-8901"],
            "phones": ["9876543219", "9876543213"],
            "orgs": ["Odisha Transport Network"],
            "location": "Rourkela",
            "description": (
                "Karan Shah was identified alongside Suresh Patel "
                "during a transport investigation."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0017",
            "fir_number": "301/2026",
            "persons": ["Arjun Mehta", "Neha Sharma"],
            "vehicles": ["OD-05-AB-1234"],
            "phones": ["9876543210", "9876543214"],
            "orgs": ["Eastern Logistics"],
            "location": "Cuttack",
            "description": (
                "Arjun Mehta and Neha Sharma were connected through "
                "records from a warehouse investigation."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0018",
            "fir_number": "315/2026",
            "persons": ["Ravi Das", "Priya Nanda"],
            "vehicles": ["OD-02-CD-5678"],
            "phones": ["9876543211", "9876543215"],
            "orgs": ["Coastal Traders"],
            "location": "Bhubaneswar",
            "description": (
                "Ravi Das and Priya Nanda were identified in "
                "communications under investigation."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0019",
            "fir_number": "327/2026",
            "persons": ["Vikram Singh", "Rohit Jena"],
            "vehicles": ["OD-33-EF-9012"],
            "phones": ["9876543212", "9876543217"],
            "orgs": ["Blue River Exports"],
            "location": "Puri",
            "description": (
                "Vikram Singh and Rohit Jena were associated with "
                "a suspicious financial movement."
            ),
        },
        {
            "case_id": "SIH-CRIME-2026-0020",
            "fir_number": "341/2026",
            "persons": ["Suresh Patel", "Karan Shah"],
            "vehicles": ["OD-14-GH-3456"],
            "phones": ["9876543213", "9876543219"],
            "orgs": ["Odisha Transport Network"],
            "location": "Rourkela",
            "description": (
                "Suresh Patel and Karan Shah were identified in "
                "a transport-related investigation."
            ),
        },
    ]

    records = []

    for index, item in enumerate(fir_data):

        records.append(
            FIRRecord(
                case_id=item["case_id"],
                fir_number=item["fir_number"],

                police_station=(
                    f"{item['location']} Central Police Station"
                ),

                district=item["location"],
                state="Odisha",

                registration_date=fake_date(index),
                incident_date=fake_date(index - 1, 3),

                incident_location=item["location"],
                description=item["description"],

                persons_mentioned=item["persons"],
                vehicles_mentioned=item["vehicles"],
                phones_mentioned=item["phones"],
                organizations_mentioned=item["orgs"],
                locations_mentioned=[item["location"]],

                status="Open",

                source_file=f"fake_fir_{index + 1:02d}.pdf",
                source_hash=source_hash(
                    f"fake_fir_{index + 1:02d}.pdf"
                ),
            )
        )

    return records


# ================================================================
# 2. CONTACT / CDR RECORDS
# ================================================================

def create_contact_records() -> list[ContactRecord]:
    """
    Create 20 fictional CDR/contact records.

    The phone numbers correspond to PEOPLE so that PHONE and
    PERSON lookups can connect FIRs to contact records.
    """

    connections = [
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 6),
        (6, 7),
        (7, 8),
        (8, 9),
        (9, 0),

        (0, 2),
        (1, 3),
        (2, 4),
        (3, 5),
        (4, 6),
        (5, 7),
        (6, 8),
        (7, 9),
        (8, 0),
        (9, 1),
    ]

    records = []

    for index, (caller_index, receiver_index) in enumerate(connections):

        caller = get_person(caller_index)
        receiver = get_person(receiver_index)

        records.append(
            ContactRecord(
                caller_name=caller["name"],
                caller_phone=caller["phone"],
                caller_location=caller["location"],

                receiver_name=receiver["name"],
                receiver_phone=receiver["phone"],
                receiver_location=receiver["location"],

                call_timestamp=fake_date(
                    index,
                    index % 8,
                ),

                duration_seconds=(
                    45 + (index * 37) % 900
                ),

                call_type=(
                    "outgoing"
                    if index % 2 == 0
                    else "incoming"
                ),

                source_file=(
                    f"fake_cdr_{index + 1:02d}.csv"
                ),

                source_hash=source_hash(
                    f"fake_cdr_{index + 1:02d}.csv"
                ),
            )
        )

    return records


# ================================================================
# 3. BANK RECORDS
# ================================================================

def create_bank_records() -> list[BankRecord]:
    """
    Create 20 fictional bank transactions.

    Accounts intentionally recur across transactions so that
    PERSON and ACCOUNT relationships can be demonstrated.
    """

    transactions = [
        (0, 1, "transfer", Decimal("125000.00")),
        (1, 2, "transfer", Decimal("84000.00")),
        (2, 3, "transfer", Decimal("215000.00")),
        (3, 4, "debit", Decimal("67500.00")),
        (4, 5, "transfer", Decimal("91000.00")),
        (5, 6, "transfer", Decimal("145000.00")),
        (6, 7, "credit", Decimal("53000.00")),
        (7, 8, "transfer", Decimal("188000.00")),
        (8, 9, "transfer", Decimal("72000.00")),
        (9, 0, "transfer", Decimal("156000.00")),

        (0, 2, "transfer", Decimal("225000.00")),
        (1, 3, "transfer", Decimal("112000.00")),
        (2, 4, "transfer", Decimal("98000.00")),
        (3, 5, "transfer", Decimal("173000.00")),
        (4, 6, "transfer", Decimal("64000.00")),
        (5, 7, "transfer", Decimal("131000.00")),
        (6, 8, "transfer", Decimal("205000.00")),
        (7, 9, "transfer", Decimal("87000.00")),
        (8, 0, "transfer", Decimal("119000.00")),
        (9, 1, "transfer", Decimal("194000.00")),
    ]

    records = []

    for index, (
        sender_index,
        receiver_index,
        transaction_type,
        amount,
    ) in enumerate(transactions):

        sender = get_person(sender_index)
        receiver = get_person(receiver_index)

        sender_account = (
            f"900100200{sender_index + 1:02d}"
        )

        receiver_account = (
            f"900200300{receiver_index + 1:02d}"
        )

        records.append(
            BankRecord(
                sender_account_number=sender_account,
                sender_account_holder_name=sender["name"],
                sender_bank_name="Odisha National Bank",
                sender_branch_name=(
                    f"{sender['location']} Main Branch"
                ),
                sender_ifsc=(
                    f"ONBK0{sender_index + 1:02d}0001"
                ),
                sender_location=sender["location"],

                receiver_account_number=receiver_account,
                receiver_account_holder_name=receiver["name"],
                receiver_bank_name="Eastern State Bank",
                receiver_branch_name=(
                    f"{receiver['location']} Branch"
                ),
                receiver_ifsc=(
                    f"ESBK0{receiver_index + 1:02d}0001"
                ),
                receiver_location=receiver["location"],

                transaction_id=(
                    f"TXN2026{index + 1:05d}"
                ),

                transaction_type=transaction_type,

                transaction_amount=amount,

                transaction_date=fake_date(
                    index,
                    2,
                ),

                currency="INR",

                source_file=(
                    f"fake_bank_{index + 1:02d}.csv"
                ),

                source_hash=source_hash(
                    f"fake_bank_{index + 1:02d}.csv"
                ),
            )
        )

    return records


# ================================================================
# 4. SOCIAL MEDIA RECORDS
# ================================================================

def create_social_records() -> list[SocialMediaRecord]:
    """
    Create 20 fictional social-media posts.

    Mentions and phone numbers deliberately overlap with the
    other source tables.
    """

    platforms = [
        "Facebook",
        "Twitter",
        "Instagram",
    ]

    records = []

    for index in range(20):

        person = get_person(index)
        mentioned = get_next_person(index)

        records.append(
            SocialMediaRecord(
                platform=platforms[index % len(platforms)],

                user_id=(
                    f"FAKEUSER{index + 1:04d}"
                ),

                username=(
                    person["name"]
                    .lower()
                    .replace(" ", "_")
                ),

                post_id=(
                    f"POST2026{index + 1:05d}"
                ),

                post_content=(
                    f"{person['name']} was seen discussing "
                    f"business activities with {mentioned['name']} "
                    f"near {person['location']}."
                ),

                post_timestamp=fake_date(
                    index,
                    5,
                ),

                likes_count=(
                    15 + index * 7
                ),

                comments_count=(
                    2 + index % 12
                ),

                shares_count=(
                    1 + index % 8
                ),

                mentioned_users=[
                    mentioned["name"],
                ],

                hashtags=[
                    "#Business",
                    "#Odisha",
                    f"#{person['location']}",
                ],

                phone_numbers=[
                    person["phone"],
                ],

                external_links=[
                    (
                        f"https://example.invalid/"
                        f"post/{index + 1}"
                    )
                ],

                source_file=(
                    f"fake_social_{index + 1:02d}.json"
                ),

                source_hash=source_hash(
                    f"fake_social_{index + 1:02d}.json"
                ),
            )
        )

    return records


# ================================================================
# 5. PREVIOUS CRIME RECORDS
# ================================================================

def create_previous_crime_records() -> list[PreviousCrimeRecord]:
    """
    Create 20 fictional criminal-history records.

    Some people intentionally have multiple historical records
    so the crime dimension of entity scoring becomes meaningful.
    """

    crime_data = [
        (0, "Property-related offense", "Financial", "Pending"),
        (1, "Vehicle theft", "Property", "Acquitted"),
        (2, "Fraud", "Financial", "Pending"),
        (3, "Illegal transport", "Organized", "Convicted"),
        (4, "Document fraud", "Financial", "Pending"),
        (5, "Cyber fraud", "Cyber", "Pending"),
        (6, "Smuggling", "Organized", "Convicted"),
        (7, "Property theft", "Property", "Acquitted"),
        (8, "Financial fraud", "Financial", "Pending"),
        (9, "Illegal transport", "Organized", "Pending"),

        (0, "Financial fraud", "Financial", "Pending"),
        (2, "Illegal transport", "Organized", "Pending"),
        (3, "Property offense", "Property", "Acquitted"),
        (5, "Document fraud", "Financial", "Pending"),
        (6, "Cyber fraud", "Cyber", "Pending"),
        (7, "Financial offense", "Financial", "Convicted"),
        (8, "Transport violation", "Organized", "Pending"),
        (9, "Fraud investigation", "Financial", "Pending"),
        (1, "Property offense", "Property", "Pending"),
        (4, "Cyber-related offense", "Cyber", "Acquitted"),
    ]

    records = []

    for index, (
        person_index,
        offense,
        category,
        status,
    ) in enumerate(crime_data):

        person = get_person(person_index)

        records.append(
            PreviousCrimeRecord(
                person_name=person["name"],

                person_identifier=(
                    f"FAKE-ID-{person_index + 1:04d}"
                ),

                case_id=(
                    f"OLD-CRIME-202{4 + index % 2}-"
                    f"{index + 1:04d}"
                ),

                fir_number=(
                    f"{500 + index}/202{4 + index % 2}"
                ),

                offense=offense,
                offense_category=category,

                case_date=fake_date(
                    -(300 - index * 5),
                    1,
                ),

                case_status=status,

                police_station=(
                    f"{person['location']} Central Police Station"
                ),

                district=person["location"],
                state="Odisha",

                description=(
                    f"Fictional historical case involving "
                    f"{person['name']} and a {category.lower()} "
                    f"offense."
                ),

                source_file=(
                    f"fake_crime_history_{index + 1:02d}.csv"
                ),

                source_hash=source_hash(
                    f"fake_crime_history_{index + 1:02d}.csv"
                ),
            )
        )

    return records


# ================================================================
# 6. SURVEILLANCE RECORDS
# ================================================================

def create_surveillance_records() -> list[SurveillanceRecord]:
    """
    Create 20 fictional surveillance observations.

    Person, vehicle and phone observations correspond to the
    same entities used in FIR/CDR/bank/social records.
    """

    records = []

    observation_types = [
        "PERSON",
        "VEHICLE",
        "PHONE",
        "PERSON",
        "VEHICLE",
    ]

    for index in range(20):

        person = get_person(index)
        observation_type = observation_types[index % len(observation_types)]

        if observation_type == "PERSON":
            entity_name = person["name"]

        elif observation_type == "VEHICLE":
            entity_name = person["vehicle"]

        else:
            entity_name = person["phone"]

        location = person["location"]

        records.append(
            SurveillanceRecord(
                entity_name=entity_name,

                entity_type=observation_type,

                camera_id=(
                    f"CCTV-{location[:3].upper()}-"
                    f"{(index % 5) + 1:02d}"
                ),

                source_type="CCTV",

                source_reference=(
                    f"CAMERA-EVENT-2026-{index + 1:04d}"
                ),

                location=location,

                location_name=(
                    f"{location} Commercial Area"
                ),

                latitude=(
                    Decimal(
                        str(
                            20.4625
                            + (index % 5) * 0.0101
                        )
                    )
                ),

                longitude=(
                    Decimal(
                        str(
                            85.8828
                            + (index % 5) * 0.0112
                        )
                    )
                ),

                observed_at=fake_date(
                    index,
                    8,
                ),

                event_description=(
                    f"Fictional surveillance observation of "
                    f"{entity_name} near {location}."
                ),

                source_file=(
                    f"fake_surveillance_{index + 1:02d}.csv"
                ),

                source_hash=source_hash(
                    f"fake_surveillance_{index + 1:02d}.csv"
                ),
            )
        )

    return records


# ================================================================
# DATASET SUMMARY
# ================================================================

def build_dataset() -> dict[str, list]:
    """
    Build the complete fake source dataset.
    """

    return {
        "fir_records": create_fir_records(),
        "contact_records": create_contact_records(),
        "bank_records": create_bank_records(),
        "social_media_records": create_social_records(),
        "previous_crime_records": create_previous_crime_records(),
        "surveillance_records": create_surveillance_records(),
    }


# ================================================================
# DATABASE CLEANUP
# ================================================================

def clear_existing_fake_data(db: Session) -> None:
    """
    Remove only records previously inserted by this fake-data
    generator.

    Real/user records are left untouched.

    The deletion order respects the FIR foreign-key dependencies.
    """

    print("Checking for existing fake data...")

    # ------------------------------------------------------------
    # Child tables first
    # ------------------------------------------------------------

    deleted = db.query(SurveillanceRecord).filter(
        SurveillanceRecord.source_file.like("fake_surveillance_%")
    ).delete(synchronize_session=False)

    print(f"  surveillance_records: deleted {deleted}")

    deleted = db.query(PreviousCrimeRecord).filter(
        PreviousCrimeRecord.source_file.like("fake_crime_history_%")
    ).delete(synchronize_session=False)

    print(f"  previous_crime_records: deleted {deleted}")

    deleted = db.query(SocialMediaRecord).filter(
        SocialMediaRecord.source_file.like("fake_social_%")
    ).delete(synchronize_session=False)

    print(f"  social_media_records: deleted {deleted}")

    deleted = db.query(BankRecord).filter(
        BankRecord.source_file.like("fake_bank_%")
    ).delete(synchronize_session=False)

    print(f"  bank_records: deleted {deleted}")

    deleted = db.query(ContactRecord).filter(
        ContactRecord.source_file.like("fake_cdr_%")
    ).delete(synchronize_session=False)

    print(f"  contact_records: deleted {deleted}")

    # ------------------------------------------------------------
    # FIR records last
    #
    # Note:
    # extracted_entities and llm_results reference FIRs through
    # foreign keys. We intentionally do not delete arbitrary FIRs.
    #
    # Fake FIR deletion is safe only when dependent analysis rows
    # have already been removed/cascaded.
    # ------------------------------------------------------------

    fake_firs = db.query(FIRRecord).filter(
        FIRRecord.source_file.like("fake_fir_%")
    ).all()

    for fir in fake_firs:
        db.delete(fir)

    print(
        f"  fir_records: marked {len(fake_firs)} fake FIRs for deletion"
    )


# ================================================================
# INSERT DATA
# ================================================================

def insert_dataset(
    db: Session,
    dataset: dict[str, list],
) -> dict[str, int]:
    """
    Insert all source records into PostgreSQL.
    """

    counts = {}

    for table_name, records in dataset.items():

        add_records(db, records)

        counts[table_name] = len(records)

        print(
            f"  prepared {len(records):2d} "
            f"{table_name}"
        )

    return counts


# ================================================================
# MAIN SEED FUNCTION
# ================================================================

def seed_database() -> None:
    """
    Main database seeding workflow.
    """

    print()
    print("=" * 64)
    print("SIH26189 — FAKE DATA SEEDER")
    print("=" * 64)
    print()

    # ------------------------------------------------------------
    # Make sure tables exist
    # ------------------------------------------------------------

    print("1. Verifying database schema...")
    init_db()
    print()

    # ------------------------------------------------------------
    # Open DB session
    # ------------------------------------------------------------

    db = SessionLocal()

    try:

        # --------------------------------------------------------
        # Remove previous fake dataset
        # --------------------------------------------------------

        print("2. Removing previous fake dataset...")

        clear_existing_fake_data(db)

        db.flush()

        print()

        # --------------------------------------------------------
        # Build data
        # --------------------------------------------------------

        print("3. Building interconnected fake dataset...")

        dataset = build_dataset()

        print()

        # --------------------------------------------------------
        # Insert data
        # --------------------------------------------------------

        print("4. Inserting source records...")

        counts = insert_dataset(
            db,
            dataset,
        )

        # --------------------------------------------------------
        # Commit
        # --------------------------------------------------------

        db.commit()

        print()
        print("5. Database commit successful.")
        print()

        # --------------------------------------------------------
        # Summary
        # --------------------------------------------------------

        print("=" * 64)
        print("FAKE DATA INSERTION COMPLETE")
        print("=" * 64)

        total = 0

        for table_name, count in counts.items():
            print(
                f"{table_name:<30} {count:>5}"
            )

            total += count

        print("-" * 64)
        print(
            f"{'TOTAL SOURCE RECORDS':<30} {total:>5}"
        )

        print("=" * 64)
        print()

        print("Network entities:")
        print(
            f"  People          : {len(PEOPLE)}"
        )
        print(
            f"  Organizations   : {len(ORGANIZATIONS)}"
        )
        print(
            f"  Locations       : {len(LOCATIONS)}"
        )

        print()
        print("Next step:")
        print(
            "Upload/analyse an FIR so NER + cross-lookup can "
            "discover these relationships."
        )
        print()

    except Exception as exc:

        db.rollback()

        print()
        print("=" * 64)
        print("FAKE DATA INSERTION FAILED")
        print("=" * 64)
        print()
        print(f"Error: {exc}")
        print()

        raise

    finally:
        db.close()


# ================================================================
# SCRIPT ENTRY POINT
# ================================================================

if __name__ == "__main__":
    seed_database()