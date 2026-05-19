"""
Pydantic schemas for User resource.

Separates concerns:
- UserBase: shared fields
- UserCreate: registration input (includes password)
- UserUpdate: partial update input
- UserResponse: public-facing output (no password)
- UserInDB: internal representation including hashed_password
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Fields shared across all User schemas."""

    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True


class UserCreate(UserBase):
    """Schema for user registration. Password is required."""

    password: str = Field(min_length=8, max_length=100, description="Plain-text password")


class UserUpdate(BaseModel):
    """Schema for updating user profile. All fields are optional."""

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=100)
    is_active: bool | None = None


class UserResponse(UserBase):
    """Public user representation returned by API endpoints (no password)."""

    model_config = ConfigDict(from_attributes=True)  # Enable ORM mode

    id: uuid.UUID
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class UserInDB(UserResponse):
    """Internal representation including hashed_password (never serialized to API)."""

    hashed_password: str
