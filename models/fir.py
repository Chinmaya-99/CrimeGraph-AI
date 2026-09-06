from sqlalchemy import (
    Column, BigInteger, String, Text,
    TIMESTAMP, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from data_base.database import Base

class FIRRecord(Base):
    __tablename__ = "fir_records"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # matches: fir_id BIGSERIAL PRIMARY KEY
    # ----------------------------------------------------------------
    fir_id                  = Column(BigInteger, primary_key=True, autoincrement=True)

    # ----------------------------------------------------------------
    # CASE DETAILS
    # matches: VARCHAR(100) NOT NULL / VARCHAR(255) nullable
    # ----------------------------------------------------------------
    case_id                 = Column(String(100), nullable=False)
    fir_number              = Column(String(100), nullable=True)
    police_station          = Column(String(255), nullable=True)
    district                = Column(String(255), nullable=True)
    state                   = Column(String(255), nullable=True)

    # ----------------------------------------------------------------
    # DATES
    # matches: TIMESTAMP nullable
    # ----------------------------------------------------------------
    registration_date       = Column(TIMESTAMP, nullable=True)
    incident_date           = Column(TIMESTAMP, nullable=True)

    # ----------------------------------------------------------------
    # CONTENT
    # matches: TEXT nullable / TEXT NOT NULL
    # ----------------------------------------------------------------
    incident_location       = Column(Text, nullable=True)
    description             = Column(Text, nullable=False)

    # ----------------------------------------------------------------
    # NER OUTPUT — JSONB arrays
    # matches: JSONB DEFAULT '[]'::jsonb
    # server_default keeps it consistent with your SQL schema
    # ----------------------------------------------------------------
    persons_mentioned       = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    vehicles_mentioned      = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    phones_mentioned        = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    organizations_mentioned = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)
    locations_mentioned     = Column(JSONB, server_default=text("'[]'::jsonb"), nullable=True)

    # ----------------------------------------------------------------
    # STATUS
    # matches: VARCHAR(50) DEFAULT 'Open'
    # ----------------------------------------------------------------
    status                  = Column(String(50), server_default=text("'Open'"), nullable=True)

    # ----------------------------------------------------------------
    # BLOCKCHAIN PROVENANCE
    # matches: VARCHAR(500) / VARCHAR(64) nullable
    # ----------------------------------------------------------------
    source_file             = Column(String(500), nullable=True)
    source_hash             = Column(String(64),  nullable=True)

    # ----------------------------------------------------------------
    # TIMESTAMPS
    # matches: TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    # NOTE: no DB trigger for updated_at in your schema,
    #       so we just let the DB handle both via server_default
    # ----------------------------------------------------------------
    created_at              = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=True)
    updated_at              = Column(TIMESTAMP, server_default=text("CURRENT_TIMESTAMP"), nullable=True)

    # ----------------------------------------------------------------
    # RELATIONSHIPS
    # one FIR → many extracted entities
    # one FIR → many LLM reasoning results
    # ----------------------------------------------------------------
    extracted_entities      = relationship(
        "ExtractedEntity",
        back_populates="fir",
        cascade="all, delete-orphan"
    )
    llm_results             = relationship(
        "LLMReasoningResult",
        back_populates="fir",
        cascade="all, delete-orphan"
    )

    # ----------------------------------------------------------------
    # REPR
    # ----------------------------------------------------------------
    def __repr__(self):
        return (
            f"<FIRRecord "
            f"fir_id={self.fir_id} "
            f"case_id={self.case_id!r} "
            f"status={self.status!r}>"
        )

    # ----------------------------------------------------------------
    # to_dict — used in Step 5 to pass FIR data to Groq LLM
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "fir_id":                   self.fir_id,
            "case_id":                  self.case_id,
            "fir_number":               self.fir_number,
            "police_station":           self.police_station,
            "district":                 self.district,
            "state":                    self.state,
            "registration_date":        str(self.registration_date) if self.registration_date else None,
            "incident_date":            str(self.incident_date) if self.incident_date else None,
            "incident_location":        self.incident_location,
            "description":              self.description,
            "persons_mentioned":        self.persons_mentioned or [],
            "vehicles_mentioned":       self.vehicles_mentioned or [],
            "phones_mentioned":         self.phones_mentioned or [],
            "organizations_mentioned":  self.organizations_mentioned or [],
            "locations_mentioned":      self.locations_mentioned or [],
            "status":                   self.status,
            "source_file":              self.source_file,
            "source_hash":              self.source_hash,
        }