"""
User Management Routes.

Endpoints:
- GET  /users/me        — Get current authenticated user profile
- PUT  /users/me        — Update current user's profile
- GET  /users/          — List all users (superuser only)
- GET  /users/{user_id} — Get user by ID (superuser only)
- DELETE /users/{user_id} — Delete user (superuser only)
"""

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DBSession, SuperUser
from app.core.logging import get_logger
from app.crud.user import user_crud
from app.schemas.user import UserResponse, UserUpdate

logger = get_logger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


# =============================================================================
# Current User Endpoints (any authenticated user)
# =============================================================================

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(current_user: CurrentUser) -> UserResponse:
    """Return the profile of the currently authenticated user."""
    return UserResponse.model_validate(current_user)


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update current user profile",
)
async def update_me(
    user_update: UserUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> UserResponse:
    """
    Update the authenticated user's own profile.

    Only the fields provided in the request body are updated.
    Users cannot grant themselves superuser access through this endpoint.
    """
    # Prevent self-privilege escalation
    if user_update.model_dump(exclude_unset=True).get("is_active") is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    # Check email uniqueness if being updated
    if user_update.email and user_update.email != current_user.email:
        existing = await user_crud.get_by_email(db, email=user_update.email)
        if existing and existing.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This email address is already in use",
            )

    updated = await user_crud.update(db, db_user=current_user, obj_in=user_update)
    logger.info("User profile updated", extra={"user_id": str(current_user.id)})
    return UserResponse.model_validate(updated)


# =============================================================================
# Admin Endpoints (superuser only)
# =============================================================================

@router.get(
    "/",
    response_model=list[UserResponse],
    summary="List all users (admin only)",
)
async def list_users(
    db: DBSession,
    _: SuperUser,
    skip: int = 0,
    limit: int = 100,
) -> list[UserResponse]:
    """Paginated list of all users. Requires superuser privileges."""
    users = await user_crud.list(db, skip=skip, limit=limit)
    return [UserResponse.model_validate(u) for u in users]


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID (admin only)",
)
async def get_user(
    user_id: uuid.UUID,
    db: DBSession,
    _: SuperUser,
) -> UserResponse:
    """Fetch any user by UUID. Requires superuser privileges."""
    user = await user_crud.get(db, user_id=user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    return UserResponse.model_validate(user)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user (admin only)",
)
async def delete_user(
    user_id: uuid.UUID,
    db: DBSession,
    current_user: SuperUser,
) -> None:
    """Hard-delete a user by ID. Requires superuser privileges."""
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )
    deleted = await user_crud.delete(db, user_id=user_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    logger.info("User deleted", extra={"deleted_user_id": str(user_id), "by": str(current_user.id)})
