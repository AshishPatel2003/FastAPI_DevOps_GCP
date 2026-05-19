"""
FastAPI Dependency Injection.

Centralizes all reusable dependencies:
- Database session
- Redis client
- Current user extraction from JWT
- Role-based access control guards
"""

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import decode_token
from app.crud.user import user_crud
from app.db.session import get_db
from app.models.user import User
from app.services.redis_service import TokenBlacklist, get_redis

logger = get_logger(__name__)

# HTTPBearer extracts "Authorization: Bearer <token>" header
_bearer_scheme = HTTPBearer(auto_error=True)


# =============================================================================
# Database
# =============================================================================

DBSession = Annotated[AsyncSession, Depends(get_db)]


# =============================================================================
# Redis
# =============================================================================

def get_redis_client() -> Redis:
    """Dependency that returns the shared Redis connection pool."""
    return get_redis()


RedisClient = Annotated[Redis, Depends(get_redis_client)]


# =============================================================================
# Authentication
# =============================================================================

async def get_current_user(
    db: DBSession,
    redis: RedisClient,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(_bearer_scheme)],
) -> User:
    """
    Extract and validate the current user from the JWT Bearer token.

    Steps:
    1. Decode the JWT and extract the subject (user ID).
    2. Check the token against the Redis blacklist (logout check).
    3. Fetch the user from the database.
    4. Verify the user is active.

    Raises:
        HTTPException 401: If token is invalid, expired, blacklisted, or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials

    # 1. Decode JWT
    try:
        payload = decode_token(token)
        user_id_str: str = payload.get("sub", "")
        token_type: str = payload.get("type", "")
        if not user_id_str or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 2. Check Redis blacklist
    blacklist = TokenBlacklist(redis)
    if await blacklist.is_blacklisted(token):
        logger.warning("Blacklisted token used", extra={"sub": user_id_str})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked. Please log in again.",
        )

    # 3. Fetch user from DB
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    db_user = await user_crud.get(db, user_id=user_id)
    if db_user is None:
        raise credentials_exception

    # 4. Check user is active
    if not db_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return db_user


CurrentUser = Annotated[User, Depends(get_current_user)]


# =============================================================================
# Role Guards
# =============================================================================

async def require_superuser(current_user: CurrentUser) -> User:
    """
    Dependency that enforces superuser access.

    Raises:
        HTTPException 403: If the current user is not a superuser.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )
    return current_user


SuperUser = Annotated[User, Depends(require_superuser)]
