from sqlalchemy import (
    Column, BigInteger, String,
    TIMESTAMP, text
)
from sqlalchemy.dialects.postgresql import JSONB
from data_base.database import Base


class AuditLedger(Base):
    __tablename__ = "audit_ledger"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # ----------------------------------------------------------------
    ledger_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # ----------------------------------------------------------------
    # EVENT
    # ----------------------------------------------------------------
    event_type = Column(
        String(100),
        nullable=False
    )

    actor_id = Column(
        BigInteger,
        nullable=True
    )

    actor_role = Column(
        String(50),
        nullable=True
    )

    # ----------------------------------------------------------------
    # TARGET
    # ----------------------------------------------------------------
    target_table = Column(
        String(100),
        nullable=True
    )

    target_record_id = Column(
        BigInteger,
        nullable=True
    )

    # ----------------------------------------------------------------
    # BLOCKCHAIN HASH CHAIN
    # ----------------------------------------------------------------
    record_hash = Column(
        String(64),
        nullable=False
    )

    previous_hash = Column(
        String(64),
        nullable=True
    )

    chain_hash = Column(
        String(64),
        nullable=False
    )

    # ----------------------------------------------------------------
    # METADATA
    # ----------------------------------------------------------------
    metadata_ = Column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
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
    # REPR
    # ----------------------------------------------------------------
    def __repr__(self):
        return (
            f"<AuditLedger "
            f"ledger_id={self.ledger_id} "
            f"event_type={self.event_type!r} "
            f"chain_hash={self.chain_hash!r}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "ledger_id": self.ledger_id,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "target_table": self.target_table,
            "target_record_id": self.target_record_id,
            "record_hash": self.record_hash,
            "previous_hash": self.previous_hash,
            "chain_hash": self.chain_hash,
            "metadata": self.metadata_ or {},
            "created_at": (
                str(self.created_at)
                if self.created_at else None
            ),
        }