"""
routes/auth_route.py
====================

Authentication API.

Endpoints
---------
POST /auth/login
    Authenticate username/password and receive JWT.

POST /auth/register
    Public registration.
    New accounts are ALWAYS created as viewer.

GET /auth/me
    Return current authenticated user.

POST /auth/users
    Admin-only user creation with selectable role.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

from data_base.database import get_db
from models.users import User
from services.auth import (
    authenticate_user,
    create_access_token,
    create_user,
    update_last_login,
)
from services.rbac import (
    get_current_user,
    require_role,
)


router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ================================================================
# REQUEST MODELS
# ================================================================


class LoginRequest(BaseModel):
    username: str = Field(
        min_length=1,
        max_length=100,
    )

    password: str = Field(
        min_length=1,
        max_length=255,
    )


class RegisterRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=100,
    )

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=255,
    )

    full_name: str | None = Field(
        default=None,
        max_length=255,
    )


class AdminCreateUserRequest(BaseModel):
    username: str = Field(
        min_length=3,
        max_length=100,
    )

    email: EmailStr

    password: str = Field(
        min_length=8,
        max_length=255,
    )

    full_name: str | None = Field(
        default=None,
        max_length=255,
    )

    role: str = Field(
        default="viewer",
        min_length=1,
        max_length=50,
    )


# ================================================================
# LOGIN
# ================================================================


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticate a user and return a JWT access token.

    Uses OAuth2-compatible form data so that:
    - Swagger Authorize works
    - OAuth2PasswordBearer works
    - normal Bearer JWT authentication works
    """

    user = authenticate_user(
        db,
        form_data.username,
        form_data.password,
    )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    update_last_login(
        db,
        user,
    )

    db.commit()

    token = create_access_token(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 60 * 60,
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        },
    }

# ================================================================
# PUBLIC REGISTRATION
# ================================================================

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
):
    """
    Register a normal user.

    SECURITY:
        Public registration can NEVER select admin/investigator.

        Every public registration becomes viewer.
    """

    try:
        user = create_user(
            db,
            username=request.username,
            email=str(request.email),
            password=request.password,
            full_name=request.full_name,
            role="viewer",
        )

        db.commit()

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User registration failed.",
        )

    return {
        "message": "User registered successfully.",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
        },
    }
# ================================================================
# CURRENT USER
# ================================================================


@router.get("/me")
def get_me(
    current_user: User = Depends(
        get_current_user
    ),
):
    """
    Return information about the authenticated user.
    """

    return {
        "authenticated": True,
        "user": {
            "user_id": current_user.user_id,
            "username": current_user.username,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role,
            "is_active": current_user.is_active,
            "created_at": (
                str(current_user.created_at)
                if current_user.created_at
                else None
            ),
            "last_login": (
                str(current_user.last_login)
                if current_user.last_login
                else None
            ),
        },
    }


# ================================================================
# ADMIN USER MANAGEMENT
# ================================================================


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
)
def admin_create_user(
    request: AdminCreateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_role("admin")
    ),
):
    """
    Create a user with a selected RBAC role.

    Only administrators can call this endpoint.
    """

    try:
        user = create_user(
            db,
            username=request.username,
            email=str(request.email),
            password=request.password,
            full_name=request.full_name,
            role=request.role,
        )

        db.commit()

    except ValueError as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    except Exception:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User creation failed.",
        )

    return {
        "message": "User created successfully.",
        "created_by": current_user.username,
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
        },
    }