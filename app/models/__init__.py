"""Models package — import all models here so Alembic can detect them."""

from app.models.user import User

__all__ = ["User"]
