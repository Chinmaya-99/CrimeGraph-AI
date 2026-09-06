from sqlalchemy import (
    Column, BigInteger, String,
    TIMESTAMP, Integer, CheckConstraint, text
)
from data_base.database import Base


class ContactRecord(Base):
    __tablename__ = "contact_records"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # matches: contact_id BIGSERIAL PRIMARY KEY
    # ----------------------------------------------------------------
    contact_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # ----------------------------------------------------------------
    # CALLER
    # ----------------------------------------------------------------
    caller_name = Column(String(255), nullable=True)
    caller_phone = Column(String(20), nullable=False)
    caller_location = Column(String(255), nullable=True)

    # ----------------------------------------------------------------
    # RECEIVER
    # ----------------------------------------------------------------
    receiver_name = Column(String(255), nullable=True)
    receiver_phone = Column(String(20), nullable=False)
    receiver_location = Column(String(255), nullable=True)

    # ----------------------------------------------------------------
    # CALL DETAILS
    # ----------------------------------------------------------------
    call_timestamp = Column(TIMESTAMP, nullable=False)
    duration_seconds = Column(
        Integer,
        server_default=text("0"),
        nullable=True
    )
    call_type = Column(String(30), nullable=True)

    source_file = Column(String(500), nullable=True)
    source_hash = Column(String(64), nullable=True)

    # ----------------------------------------------------------------
    # CONSTRAINTS
    # matches: CHECK (duration_seconds >= 0)
    # ----------------------------------------------------------------
    __table_args__ = (
        CheckConstraint(
            "duration_seconds >= 0",
            name="check_duration_seconds_positive"
        ),
    )

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
            f"<ContactRecord "
            f"contact_id={self.contact_id} "
            f"caller_phone={self.caller_phone!r} "
            f"receiver_phone={self.receiver_phone!r}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "contact_id": self.contact_id,
            "caller_name": self.caller_name,
            "caller_phone": self.caller_phone,
            "caller_location": self.caller_location,
            "receiver_name": self.receiver_name,
            "receiver_phone": self.receiver_phone,
            "receiver_location": self.receiver_location,
            "call_timestamp": (
                str(self.call_timestamp)
                if self.call_timestamp else None
            ),
            "duration_seconds": self.duration_seconds,
            "call_type": self.call_type,
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "created_at": (
                str(self.created_at)
                if self.created_at else None
            ),
        }