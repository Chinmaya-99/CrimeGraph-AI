from sqlalchemy import (
    Column, BigInteger, String,
    TIMESTAMP, Numeric, CheckConstraint, text
)
from sqlalchemy.orm import relationship
from data_base.database import Base


class BankRecord(Base):
    __tablename__ = "bank_records"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # ----------------------------------------------------------------
    bank_record_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # ----------------------------------------------------------------
    # SENDER
    # ----------------------------------------------------------------
    sender_account_number = Column(
        String(50),
        nullable=False
    )
    sender_account_holder_name = Column(
        String(255),
        nullable=False
    )
    sender_bank_name = Column(String(255), nullable=True)
    sender_branch_name = Column(String(255), nullable=True)
    sender_ifsc = Column(String(20), nullable=True)
    sender_location = Column(String(255), nullable=True)

    # ----------------------------------------------------------------
    # RECEIVER
    # ----------------------------------------------------------------
    receiver_account_number = Column(
        String(50),
        nullable=False
    )
    receiver_account_holder_name = Column(
        String(255),
        nullable=False
    )
    receiver_bank_name = Column(String(255), nullable=True)
    receiver_branch_name = Column(String(255), nullable=True)
    receiver_ifsc = Column(String(20), nullable=True)
    receiver_location = Column(String(255), nullable=True)

    # ----------------------------------------------------------------
    # TRANSACTION
    # ----------------------------------------------------------------
    transaction_id = Column(String(100), nullable=True)
    transaction_type = Column(String(50), nullable=True)

    transaction_amount = Column(
        Numeric(15, 2),
        nullable=False
    )

    transaction_date = Column(TIMESTAMP, nullable=True)

    currency = Column(
        String(10),
        server_default=text("'INR'"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # CONSTRAINT
    # ----------------------------------------------------------------
    __table_args__ = (
        CheckConstraint(
            "transaction_amount >= 0",
            name="check_transaction_amount_positive"
        ),
    )

    # ----------------------------------------------------------------
    # PROVENANCE
    # ----------------------------------------------------------------
    source_file = Column(String(500), nullable=True)
    source_hash = Column(String(64), nullable=True)

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
            f"<BankRecord "
            f"bank_record_id={self.bank_record_id} "
            f"transaction_id={self.transaction_id!r} "
            f"amount={self.transaction_amount}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "bank_record_id": self.bank_record_id,
            "sender_account_number": self.sender_account_number,
            "sender_account_holder_name": self.sender_account_holder_name,
            "sender_bank_name": self.sender_bank_name,
            "sender_branch_name": self.sender_branch_name,
            "sender_ifsc": self.sender_ifsc,
            "sender_location": self.sender_location,
            "receiver_account_number": self.receiver_account_number,
            "receiver_account_holder_name": self.receiver_account_holder_name,
            "receiver_bank_name": self.receiver_bank_name,
            "receiver_branch_name": self.receiver_branch_name,
            "receiver_ifsc": self.receiver_ifsc,
            "receiver_location": self.receiver_location,
            "transaction_id": self.transaction_id,
            "transaction_type": self.transaction_type,
            "transaction_amount": (
                float(self.transaction_amount)
                if self.transaction_amount is not None
                else None
            ),
            "transaction_date": (
                str(self.transaction_date)
                if self.transaction_date else None
            ),
            "currency": self.currency,
            "source_file": self.source_file,
            "source_hash": self.source_hash,
            "created_at": (
                str(self.created_at)
                if self.created_at else None
            ),
        }