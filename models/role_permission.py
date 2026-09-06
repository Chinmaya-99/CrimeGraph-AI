from sqlalchemy import (
    Column, BigInteger, String, Boolean, UniqueConstraint
)
from data_base.database import Base


class RolePermission(Base):
    __tablename__ = "role_permissions"

    # ----------------------------------------------------------------
    # PRIMARY KEY
    # ----------------------------------------------------------------
    permission_id = Column(
        BigInteger,
        primary_key=True,
        autoincrement=True
    )

    # ----------------------------------------------------------------
    # RBAC
    # ----------------------------------------------------------------
    role = Column(
        String(50),
        nullable=False
    )

    resource = Column(
        String(100),
        nullable=False
    )

    can_read = Column(
        Boolean,
        default=False,
        nullable=True
    )

    can_write = Column(
        Boolean,
        default=False,
        nullable=True
    )

    can_delete = Column(
        Boolean,
        default=False,
        nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "role",
            "resource",
            name="uq_role_permissions_role_resource",
        ),
    )

    # ----------------------------------------------------------------
    # REPR
    # ----------------------------------------------------------------
    def __repr__(self):
        return (
            f"<RolePermission "
            f"permission_id={self.permission_id} "
            f"role={self.role!r} "
            f"resource={self.resource!r}>"
        )

    # ----------------------------------------------------------------
    # TO DICT
    # ----------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "permission_id": self.permission_id,
            "role": self.role,
            "resource": self.resource,
            "can_read": self.can_read,
            "can_write": self.can_write,
            "can_delete": self.can_delete,
        }