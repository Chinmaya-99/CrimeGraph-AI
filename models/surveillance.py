from sqlalchemy import (
    Column, BigInteger, String,
    TIMESTAMP, Numeric, Text, text
)
from data_base.database import Base


class SurveillanceRecord(Base):
    __tablename__ = "surveillance_records"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # ----------------------------------------------------------------
    surveillance_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # ----------------------------------------------------------------
    # OBSERVED ENTITY
    # ----------------------------------------------------------------
    entity_name = Column(String(255), nullable=True)
    entity_type = Column(String(50), nullable=True)

    # ----------------------------------------------------------------
    # SURVEILLANCE SOURCE
    # ----------------------------------------------------------------
    camera_id = Column(String(100), nullable=True)
    source_type = Column(String(100), nullable=True)
    source_reference = Column(String(255), nullable=True)

    # ----------------------------------------------------------------
    # LOCATION
    # ----------------------------------------------------------------
    location = Column(String(255), nullable=False)
    location_name = Column(String(255), nullable=True)

    latitude = Column(
        Numeric(10, 7),
        nullable=True
    )

    longitude = Column(
        Numeric(10, 7),
        nullable=True
    )

    # ----------------------------------------------------------------
    # OBSERVATION
    # ----------------------------------------------------------------
    observed_at = Column(TIMESTAMP, nullable=True)
    event_description = Column(Text, nullable=True)

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
            f"<SurveillanceRecord "
            f"surveillance_id={self.surveillance_id} "
            f"entity_name={self.entity_name!r} "
            f"entity_type={self.entity_type!r}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "surveillance_id": self.surveillance_id,
            "entity_name": self.entity_name,
            "entity_type": self.entity_type,
            "camera_id": self.camera_id,
            "source_type": self.source_type,
            "source_reference": self.source_reference,
            "location": self.location,
            "location_name": self.location_name,
            "latitude": (
                float(self.latitude)
                if self.latitude is not None
                else None
            ),
            "longitude": (
                float(self.longitude)
                if self.longitude is not None
                else None
            ),
            "observed_at": (
                str(self.observed_at)
                if self.observed_at else None
            ),
            "event_description": self.event_description,
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "created_at": (
                str(self.created_at)
                if self.created_at else None
            ),
        }