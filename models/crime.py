from sqlalchemy import (
    Column, BigInteger, String,
    TIMESTAMP, Text,text
)
from data_base.database import Base


class PreviousCrimeRecord(Base):
    __tablename__ = "previous_crime_records"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # ----------------------------------------------------------------
    history_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # ----------------------------------------------------------------
    # PERSON
    # ----------------------------------------------------------------
    person_name = Column(String(255), nullable=False)
    person_identifier = Column(String(255), nullable=True)

    # ----------------------------------------------------------------
    # CASE DETAILS
    # ----------------------------------------------------------------
    case_id = Column(String(100), nullable=True)
    fir_number = Column(String(100), nullable=True)

    offense = Column(String(255), nullable=True)
    offense_category = Column(String(255), nullable=True)

    case_date = Column(TIMESTAMP, nullable=True)
    case_status = Column(String(100), nullable=True)

    # ----------------------------------------------------------------
    # POLICE / LOCATION
    # ----------------------------------------------------------------
    police_station = Column(String(255), nullable=True)
    district = Column(String(255), nullable=True)
    state = Column(String(255), nullable=True)

    description = Column(Text, nullable=True)

    # ----------------------------------------------------------------
    # BLOCKCHAIN PROVENANCE
    # ----------------------------------------------------------------
    source_file = Column(String(500), nullable=True)
    source_hash = Column(String(64), nullable=True)

    # ----------------------------------------------------------------
    # TIMESTAMP
    # ----------------------------------------------------------------
    created_at = Column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # REPR
    # ----------------------------------------------------------------
    def __repr__(self):
        return (
            f"<PreviousCrimeRecord "
            f"history_id={self.history_id} "
            f"person_name={self.person_name!r} "
            f"case_id={self.case_id!r}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "history_id": self.history_id,
            "person_name": self.person_name,
            "person_identifier": self.person_identifier,
            "case_id": self.case_id,
            "fir_number": self.fir_number,
            "offense": self.offense,
            "offense_category": self.offense_category,
            "case_date": (
                str(self.case_date)
                if self.case_date else None
            ),
            "case_status": self.case_status,
            "police_station": self.police_station,
            "district": self.district,
            "state": self.state,
            "description": self.description,
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "created_at": (
                str(self.created_at)
                if self.created_at else None
            ),
        }