"""
Authentication Routes — Clean Implementation.

Endpoints:
- POST /auth/register  — Public user registration
- POST /auth/login     — Email/password login, returns JWT pair
- POST /auth/refresh   — Refresh access token using refresh token
- POST /auth/logout    — Blacklist the current access token in Redis
"""

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from jose import JWTError

from app.api.deps import CurrentUser, DBSession, RedisClient
from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.crud.user import user_crud
from app.schemas.token import Token
from app.schemas.user import UserCreate, UserResponse
from app.services.redis_service import TokenBlacklist

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])
_bearer = HTTPBearer(auto_error=True)


# =============================================================================
# Registration
# =============================================================================

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(user_in: UserCreate, db: DBSession) -> UserResponse:
    """
    Create a new user account.

    - Validates email uniqueness.
    - Hashes password with bcrypt before storage.
    - Returns the created user profile (password excluded).
    """
    existing = await user_crud.get_by_email(db, email=user_in.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists",
        )
    user = await user_crud.create(db, obj_in=user_in)
    logger.info("New user registered", extra={"email": user_in.email})
    return UserResponse.model_validate(user)


# =============================================================================
# Login
# =============================================================================

@router.post(
    "/login",
    response_model=Token,
    summary="Login and obtain JWT access + refresh tokens",
)
async def login(
    db: DBSession,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """
    Authenticate with email (username field) and password.

    Returns a short-lived access token and a long-lived refresh token.
    Include the access token in all authenticated requests:
    `Authorization: Bearer <access_token>`
    """
    user = await user_crud.authenticate(
        db, email=form_data.username, password=form_data.password
    )
    if not user:
        logger.warning("Failed login attempt", extra={"email": form_data.username})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    access_token = create_access_token(subject=str(user.id))
    refresh_token = create_refresh_token(subject=str(user.id))

    logger.info("User authenticated", extra={"user_id": str(user.id)})
    return Token(access_token=access_token, refresh_token=refresh_token)


# =============================================================================
# Token Refresh (Rotation)
# =============================================================================

@router.post(
    "/refresh",
    response_model=Token,
    summary="Exchange refresh token for a new token pair",
)
async def refresh(
    db: DBSession,
    redis: RedisClient,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
) -> Token:
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    **Refresh Token Rotation**: The submitted refresh token is immediately
    blacklisted. A fresh pair is returned. This limits replay attack windows.

    Pass the refresh token in the `Authorization: Bearer <refresh_token>` header.
    """
    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )

    token = credentials.credentials

    # Decode & validate
    try:
        payload = decode_token(token)
        if payload.get("type") != REFRESH_TOKEN_TYPE:
            raise invalid_exc
        user_id_str: str = payload.get("sub", "")
    except JWTError:
        raise invalid_exc

    # Check blacklist
    blacklist = TokenBlacklist(redis)
    if await blacklist.is_blacklisted(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked. Please log in again.",
        )

    # Fetch user
    user = await user_crud.get(db, user_id=uuid.UUID(user_id_str))
    if not user or not user.is_active:
        raise invalid_exc

    # Blacklist old refresh token (rotation — prevents reuse)
    ttl = int(timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS).total_seconds())
    await blacklist.add(token, ttl)

    # Issue new pair
    new_access = create_access_token(subject=str(user.id))
    new_refresh = create_refresh_token(subject=str(user.id))

    logger.info("Token pair refreshed", extra={"user_id": str(user.id)})
    return Token(access_token=new_access, refresh_token=new_refresh)


# =============================================================================
# Logout (Token Blacklisting)
# =============================================================================

@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout and revoke access token",
)
async def logout(
    redis: RedisClient,
    current_user: CurrentUser,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer)],
) -> None:
    """
    Revoke the current access token by adding it to the Redis blacklist.

    After this call, the token cannot be used for authentication even if
    it has not yet expired. The token is stored in Redis until its natural
    expiry, then auto-deleted by Redis TTL.
    """
    token = credentials.credentials
    blacklist = TokenBlacklist(redis)

    # TTL: remaining lifetime of the access token
    ttl = int(timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES).total_seconds())
    await blacklist.add(token, ttl)

    logger.info("User logged out (token blacklisted)", extra={"user_id": str(current_user.id)})
