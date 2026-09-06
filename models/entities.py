from sqlalchemy import (
    Column, BigInteger, String, Integer,
    TIMESTAMP, Float, ForeignKey, UniqueConstraint, text
)
from sqlalchemy.orm import relationship
from data_base.database import Base


class ExtractedEntity(Base):
    __tablename__ = "extracted_entities"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # ----------------------------------------------------------------
    entity_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # ----------------------------------------------------------------
    # FIR FOREIGN KEY
    # ----------------------------------------------------------------
    fir_id = Column(
        BigInteger,
        ForeignKey("fir_records.fir_id", ondelete="CASCADE"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # ENTITY
    # ----------------------------------------------------------------
    entity_type = Column(
        String(50),
        nullable=False
    )

    entity_value = Column(
        String(255),
        nullable=False
    )

    confidence = Column(
        Float,
        server_default=text("1.0"),
        nullable=True
    )

    extraction_source = Column(
        String(100),
        nullable=True
    )

    # ----------------------------------------------------------------
    # CROSS DATABASE LOOKUP
    # ----------------------------------------------------------------
    db_hit_count = Column(
        Integer,
        server_default=text("0"),
        nullable=True,
        comment="Number of source tables that returned at least one hit",
    )

    entity_score = Column(
        Float,
        server_default=text("0.0"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # SOURCE RECORD
    # ----------------------------------------------------------------
    source_table = Column(
        String(100),
        nullable=True
    )

    source_record_id = Column(
        BigInteger,
        nullable=True
    )

    # ----------------------------------------------------------------
    # TIMESTAMP
    # ----------------------------------------------------------------
    created_at = Column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "fir_id",
            "entity_type",
            "entity_value",
            name="uq_extracted_entities_fir_type_value",
        ),
    )

    # ----------------------------------------------------------------
    # RELATIONSHIP
    # one extracted entity → one FIR
    # ----------------------------------------------------------------
    fir = relationship(
        "FIRRecord",
        back_populates="extracted_entities"
    )

    # ----------------------------------------------------------------
    # REPR
    # ----------------------------------------------------------------
    def __repr__(self):
        return (
            f"<ExtractedEntity "
            f"entity_id={self.entity_id} "
            f"entity_type={self.entity_type!r} "
            f"entity_value={self.entity_value!r}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "fir_id": self.fir_id,
            "entity_type": self.entity_type,
            "entity_value": self.entity_value,
            "confidence": self.confidence,
            "extraction_source": self.extraction_source,
            "db_hit_count": self.db_hit_count,
            "entity_score": self.entity_score,
            "source_table": self.source_table,
            "source_record_id": self.source_record_id,
            "created_at": (
                str(self.created_at)
                if self.created_at else None
            ),
        }