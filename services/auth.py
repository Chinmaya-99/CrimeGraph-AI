"""
services/auth.py
================

JWT authentication service for SIH26189.

Responsibilities
----------------
1. Hash and verify passwords.
2. Create JWT access tokens.
3. Decode and validate JWTs.
4. Load the authenticated user from PostgreSQL.
5. Bootstrap the first admin account from environment variables.

Security model
--------------
The JWT identifies the user.

PostgreSQL remains the source of truth for:
    - current role
    - is_active status
    - username/email
    - account existence

Therefore:
    JWT -> identity
    DB  -> authorization state

Environment variables
---------------------
JWT_SECRET_KEY
JWT_ALGORITHM
JWT_ACCESS_TOKEN_EXPIRE_MINUTES

Optional bootstrap admin:
ADMIN_USERNAME
ADMIN_EMAIL
ADMIN_PASSWORD
ADMIN_FULL_NAME
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from data_base.database import SessionLocal
from models.users import User


load_dotenv()


# ================================================================
# CONFIGURATION
# ================================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY is not configured. "
        "Add a strong random secret to your .env file."
    )


JWT_ALGORITHM = os.getenv(
    "JWT_ALGORITHM",
    "HS256",
)

JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv(
        "JWT_ACCESS_TOKEN_EXPIRE_MINUTES",
        "60",
    )
)


# ================================================================
# PASSWORD HASHING
# ================================================================


def hash_password(password: str) -> str:
    """
    Hash a plaintext password using bcrypt.

    The plaintext password is never stored in PostgreSQL.
    """

    if not isinstance(password, str):
        raise TypeError(
            "Password must be a string."
        )

    if not password:
        raise ValueError(
            "Password cannot be empty."
        )

    password_bytes = password.encode(
        "utf-8"
    )

    hashed = bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(),
    )

    return hashed.decode(
        "utf-8"
    )


def verify_password(
    plain_password: str,
    password_hash: str,
) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.

    Invalid/malformed hashes return False rather than exposing
    internal bcrypt errors to the API caller.
    """

    if not plain_password or not password_hash:
        return False

    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (
        ValueError,
        TypeError,
    ):
        return False


# ================================================================
# JWT
# ================================================================


def create_access_token(
    *,
    user_id: int,
    username: str,
    role: str,
) -> str:
    """
    Create a signed JWT access token.

    The role is included for convenience/debugging, but authorization
    must NOT trust this value blindly. The current role is loaded from
    PostgreSQL by get_current_user().
    """

    now = datetime.now(
        timezone.utc
    )

    expires_at = (
        now
        + timedelta(
            minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES
        )
    )

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": expires_at,
    }

    return jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(
    token: str,
) -> dict[str, Any]:
    """
    Decode and validate an access JWT.

    Raises HTTPException(401) for:
        - invalid token
        - expired token
        - wrong token type
        - missing subject
    """

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token.",
        headers={
            "WWW-Authenticate": "Bearer",
        },
    )

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
        )

    except jwt.ExpiredSignatureError:
        raise credentials_exception

    except jwt.InvalidTokenError:
        raise credentials_exception

    if payload.get("type") != "access":
        raise credentials_exception

    subject = payload.get("sub")

    if not subject:
        raise credentials_exception

    try:
        int(subject)
    except (
        TypeError,
        ValueError,
    ):
        raise credentials_exception

    return payload


# ================================================================
# USER AUTHENTICATION
# ================================================================


def authenticate_user(
    db: Session,
    username: str,
    password: str,
) -> User | None:
    """
    Authenticate a user using username + password.

    Returns:
        User object on success.
        None on failure.

    Inactive users cannot authenticate.
    """

    username = (
        username or ""
    ).strip()

    if not username or not password:
        return None

    user = (
        db.query(User)
        .filter(
            User.username == username
        )
        .first()
    )

    if user is None:
        return None

    if not user.is_active:
        return None

    if not verify_password(
        password,
        user.password_hash,
    ):
        return None

    return user


def get_user_by_id(
    db: Session,
    user_id: int,
) -> User | None:
    """
    Load a user by primary key.
    """

    return (
        db.query(User)
        .filter(
            User.user_id == user_id
        )
        .first()
    )


# ================================================================
# USER CREATION
# ================================================================


def create_user(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    full_name: str | None = None,
    role: str = "viewer",
) -> User:
    """
    Create a new user.

    This function performs application-level validation.

    Allowed roles:
        admin
        investigator
        viewer
    """

    username = (
        username or ""
    ).strip()

    email = (
        email or ""
    ).strip().lower()

    full_name = (
        full_name.strip()
        if isinstance(full_name, str)
        else None
    )

    role = (
        role or "viewer"
    ).strip().lower()

    allowed_roles = {
        "admin",
        "investigator",
        "viewer",
    }

    if role not in allowed_roles:
        raise ValueError(
            f"Unsupported role '{role}'. "
            f"Allowed roles: {sorted(allowed_roles)}"
        )

    if not username:
        raise ValueError(
            "Username is required."
        )

    if not email:
        raise ValueError(
            "Email is required."
        )

    if not password:
        raise ValueError(
            "Password is required."
        )

    existing_username = (
        db.query(User)
        .filter(
            User.username == username
        )
        .first()
    )

    if existing_username:
        raise ValueError(
            "Username already exists."
        )

    existing_email = (
        db.query(User)
        .filter(
            User.email == email
        )
        .first()
    )

    if existing_email:
        raise ValueError(
            "Email already exists."
        )

    user = User(
        username=username,
        email=email,
        password_hash=hash_password(
            password
        ),
        full_name=full_name,
        role=role,
        is_active=True,
    )

    db.add(user)
    db.flush()

    return user


# ================================================================
# ADMIN BOOTSTRAP
# ================================================================


def ensure_bootstrap_admin() -> None:
    """
    Create the initial administrator from environment variables.

    This is intentionally idempotent.

    Required environment variables:
        ADMIN_USERNAME
        ADMIN_EMAIL
        ADMIN_PASSWORD

    Optional:
        ADMIN_FULL_NAME

    If the username already exists, nothing is changed.

    This avoids exposing a public "create admin" API.
    """

    username = (
        os.getenv("ADMIN_USERNAME")
        or ""
    ).strip()

    email = (
        os.getenv("ADMIN_EMAIL")
        or ""
    ).strip().lower()

    password = (
        os.getenv("ADMIN_PASSWORD")
        or ""
    )

    full_name = (
        os.getenv("ADMIN_FULL_NAME")
        or "System Administrator"
    ).strip()

    if not username and not email and not password:
        return

    if not username or not email or not password:
        raise RuntimeError(
            "Bootstrap admin configuration is incomplete. "
            "Set ADMIN_USERNAME, ADMIN_EMAIL and ADMIN_PASSWORD "
            "together."
        )

    db = SessionLocal()

    try:
        existing_user = (
            db.query(User)
            .filter(
                User.username == username
            )
            .first()
        )

        if existing_user:
            return

        existing_email = (
            db.query(User)
            .filter(
                User.email == email
            )
            .first()
        )

        if existing_email:
            raise RuntimeError(
                "ADMIN_EMAIL is already associated with another user."
            )

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(
                password
            ),
            full_name=full_name,
            role="admin",
            is_active=True,
        )

        db.add(user)
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ================================================================
# LAST LOGIN
# ================================================================


def update_last_login(
    db: Session,
    user: User,
) -> None:
    """
    Update the user's last successful login timestamp.
    """

    user.last_login = datetime.now(
        timezone.utc
    )

    db.flush()