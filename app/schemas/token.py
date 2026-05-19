"""Pydantic schemas for JWT token responses."""

from pydantic import BaseModel


class Token(BaseModel):
    """Access + refresh token pair returned on successful login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """Decoded JWT payload structure."""

    sub: str
    type: str  # "access" or "refresh"
    exp: int
    iat: int
