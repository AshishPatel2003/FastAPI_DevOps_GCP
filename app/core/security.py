 """
JWT Security Utilities.

Handles token creation, verification, and password hashing.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# Password hashing context — bcrypt with automatic salt
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token types
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


# =============================================================================
# Password Utilities
# =============================================================================


def hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


# =============================================================================
# JWT Token Utilities
# =============================================================================


def create_access_token(subject: str | Any, extra_claims: dict | None = None) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: The token subject (usually user ID or email).
        extra_claims: Optional additional claims to embed.

    Returns:
        Signed JWT string.
    """
    expire = datetime.now(UTC) + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": ACCESS_TOKEN_TYPE,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: str | Any) -> str:
    """
    Create a signed JWT refresh token (longer expiry, fewer claims).

    Args:
        subject: The token subject (usually user ID).

    Returns:
        Signed JWT string.
    """
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": REFRESH_TOKEN_TYPE,
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Args:
        token: The JWT string to decode.

    Returns:
        Decoded payload dict.

    Raises:
        JWTError: If the token is invalid, expired, or tampered with.
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


def get_token_subject(token: str) -> str:
    """
    Extract the subject claim from a token without raising complex errors.

    Returns:
        Subject string or empty string on failure.
    """
    try:
        payload = decode_token(token)
        return payload.get("sub", "")
    except JWTError:
        return ""
