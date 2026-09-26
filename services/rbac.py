"""
services/rbac.py
================

Role-Based Access Control for SIH26189.

Authorization flow
------------------

JWT
 ↓
get_current_user()
 ↓
current User from PostgreSQL
 ↓
require_permission(resource, action)
 ↓
role_permissions
 ↓
ALLOW / 403
"""

from __future__ import annotations

from typing import Callable
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from data_base.database import get_db
from models.role_permission import RolePermission
from models.users import User
from services.auth import (
    decode_access_token,
    get_user_by_id,
)


# ================================================================
# CURRENT USER
# ================================================================
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/auth/login"
)

def get_current_user(
    token: str = Depends(
    oauth2_scheme
),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the currently authenticated user.

    Important:
        The role is loaded from PostgreSQL, not trusted from JWT.

    Therefore:
        - disabled users are rejected immediately
        - changed roles take effect immediately
        - deleted users cannot continue using old tokens
    """

    payload = decode_access_token(
        token
    )

    try:
        user_id = int(
            payload["sub"]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    user = get_user_by_id(
        db,
        user_id,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive.",
        )

    return user


# ================================================================
# ROLE CHECK
# ================================================================


def require_role(
    *allowed_roles: str,
) -> Callable:
    """
    Require the authenticated user to have one of the supplied roles.

    Example:

        @router.get("/admin-only")
        def admin_only(
            current_user: User = Depends(
                require_role("admin")
            )
        ):
            ...
    """

    normalized_roles = {
        role.strip().lower()
        for role in allowed_roles
    }

    if not normalized_roles:
        raise ValueError(
            "require_role() requires at least one role."
        )

    def dependency(
        current_user: User = Depends(
            get_current_user
        ),
    ) -> User:

        current_role = (
            current_user.role or ""
        ).strip().lower()

        if current_role not in normalized_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role privileges.",
            )

        return current_user

    return dependency


# ================================================================
# PERMISSION CHECK
# ================================================================


def require_permission(
    resource: str,
    action: str,
) -> Callable:
    """
    Require a specific RBAC permission.

    Supported actions:
        read
        write
        delete

    Permission is resolved from:
        role_permissions.role
        role_permissions.resource
        role_permissions.can_read
        role_permissions.can_write
        role_permissions.can_delete
    """

    resource = (
        resource or ""
    ).strip().lower()

    action = (
        action or ""
    ).strip().lower()

    allowed_actions = {
        "read",
        "write",
        "delete",
    }

    if not resource:
        raise ValueError(
            "RBAC resource cannot be empty."
        )

    if action not in allowed_actions:
        raise ValueError(
            f"Unsupported RBAC action '{action}'. "
            f"Allowed actions: {sorted(allowed_actions)}"
        )

    permission_column_map = {
        "read": RolePermission.can_read,
        "write": RolePermission.can_write,
        "delete": RolePermission.can_delete,
    }

    permission_column = permission_column_map[
        action
    ]

    def dependency(
        current_user: User = Depends(
            get_current_user
        ),
        db: Session = Depends(
            get_db
        ),
    ) -> User:

        role = (
            current_user.role or ""
        ).strip().lower()

        permission = (
            db.query(RolePermission)
            .filter(
                RolePermission.role == role,
                RolePermission.resource == resource,
            )
            .first()
        )

        if permission is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{role}' has no permission "
                    f"for resource '{resource}'."
                ),
            )

        if not bool(
            getattr(
                permission,
                permission_column.key,
                False,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{role}' does not have "
                    f"{action} permission for "
                    f"'{resource}'."
                ),
            )

        return current_user

    return dependency