from sqlalchemy import (
    Column, BigInteger, String,
    TIMESTAMP, Integer, Text,
    ForeignKey, text
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from data_base.database import Base


class LLMReasoningResult(Base):
    __tablename__ = "llm_reasoning_results"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # ----------------------------------------------------------------
    reasoning_id = Column(
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
    # RAW LLM OUTPUT
    # ----------------------------------------------------------------
    raw_response = Column(
        Text,
        nullable=True
    )

    # ----------------------------------------------------------------
    # PARSED RELATIONS
    # ----------------------------------------------------------------
    relations = Column(
        JSONB,
        server_default=text("'[]'::jsonb"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # SUSPICIOUS FLAGS
    # ----------------------------------------------------------------
    suspicious_flags = Column(
        JSONB,
        server_default=text("'[]'::jsonb"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # MODEL INFORMATION
    # ----------------------------------------------------------------
    model_used = Column(
        String(100),
        nullable=True
    )

    prompt_tokens = Column(
        Integer,
        nullable=True
    )

    completion_tokens = Column(
        Integer,
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

    # ----------------------------------------------------------------
    # RELATIONSHIP
    # ----------------------------------------------------------------
    fir = relationship(
        "FIRRecord",
        back_populates="llm_results"
    )

    # ----------------------------------------------------------------
    # REPR
    # ----------------------------------------------------------------
    def __repr__(self):
        return (
            f"<LLMReasoningResult "
            f"reasoning_id={self.reasoning_id} "
            f"fir_id={self.fir_id} "
            f"model_used={self.model_used!r}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "reasoning_id": self.reasoning_id,
            "fir_id": self.fir_id,
            "raw_response": self.raw_response,
            "relations": self.relations or [],
            "suspicious_flags": self.suspicious_flags or [],
            "model_used": self.model_used,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "created_at": (
                str(self.created_at)
                if self.created_at else None
            ),
        }