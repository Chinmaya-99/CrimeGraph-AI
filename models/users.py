from sqlalchemy import (
    Column, BigInteger, String,
    TIMESTAMP, Boolean, text
)
from data_base.database import Base


class User(Base):
    __tablename__ = "users"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # ----------------------------------------------------------------
    user_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # ----------------------------------------------------------------
    # USER DETAILS
    # ----------------------------------------------------------------
    username = Column(
        String(100),
        unique=True,
        nullable=False
    )

    email = Column(
        String(255),
        unique=True,
        nullable=False
    )

    password_hash = Column(
        String(255),
        nullable=False
    )

    full_name = Column(
        String(255),
        nullable=True
    )

    # ----------------------------------------------------------------
    # RBAC
    # ----------------------------------------------------------------
    role = Column(
        String(50),
        server_default=text("'viewer'"),
        nullable=False
    )

    is_active = Column(
        Boolean,
        server_default=text("TRUE"),
        nullable=True
    )

    # ----------------------------------------------------------------
    # TIMESTAMPS
    # ----------------------------------------------------------------
    created_at = Column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=True
    )

    last_login = Column(
        TIMESTAMP,
        nullable=True
    )

    # ----------------------------------------------------------------
    # REPR
    # ----------------------------------------------------------------
    def __repr__(self):
        return (
            f"<User "
            f"user_id={self.user_id} "
            f"username={self.username!r} "
            f"role={self.role!r}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": (
                str(self.created_at)
                if self.created_at else None
            ),
            "last_login": (
                str(self.last_login)
                if self.last_login else None
            ),
        }