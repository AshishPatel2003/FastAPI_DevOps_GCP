"""
User CRUD operations.

Thin data-access layer — no business logic here.
Business rules (e.g., "you can't deactivate yourself") live in service/route layers.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserCRUD:
    """CRUD operations for the User model."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(self, db: AsyncSession, *, user_id: uuid.UUID) -> User | None:
        """Fetch user by primary key (UUID)."""
        result = await db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, db: AsyncSession, *, email: str) -> User | None:
        """Fetch user by email address (case-sensitive)."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def list(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100
    ) -> list[User]:
        """Paginated list of all users."""
        result = await db.execute(select(User).offset(skip).limit(limit))
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create(
        self,
        db: AsyncSession,
        *,
        obj_in: UserCreate,
        is_superuser: bool = False,
    ) -> User:
        """Create a new user, hashing the password before storage."""
        db_user = User(
            email=obj_in.email,
            full_name=obj_in.full_name,
            hashed_password=hash_password(obj_in.password),
            is_active=obj_in.is_active,
            is_superuser=is_superuser,
        )
        db.add(db_user)
        await db.flush()  # Get the generated UUID without committing
        await db.refresh(db_user)
        return db_user

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update(
        self,
        db: AsyncSession,
        *,
        db_user: User,
        obj_in: UserUpdate,
    ) -> User:
        """Update user fields. Only provided (non-None) fields are updated."""
        update_data = obj_in.model_dump(exclude_unset=True)

        if "password" in update_data:
            update_data["hashed_password"] = hash_password(update_data.pop("password"))

        for field, value in update_data.items():
            setattr(db_user, field, value)

        db.add(db_user)
        await db.flush()
        await db.refresh(db_user)
        return db_user

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete(self, db: AsyncSession, *, user_id: uuid.UUID) -> User | None:
        """Hard-delete a user by ID. Returns deleted user or None if not found."""
        db_user = await self.get(db, user_id=user_id)
        if db_user:
            await db.delete(db_user)
            await db.flush()
        return db_user

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    async def authenticate(
        self, db: AsyncSession, *, email: str, password: str
    ) -> User | None:
        """
        Validate email + password combination.

        Returns:
            User object if credentials are valid, None otherwise.
        """
        from app.core.security import verify_password

        db_user = await self.get_by_email(db, email=email)
        if not db_user:
            return None
        if not verify_password(password, db_user.hashed_password):
            return None
        return db_user


# Module-level singleton — import this in routes/services
user_crud = UserCRUD()
