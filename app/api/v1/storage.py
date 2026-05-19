"""
Storage Routes.

Endpoints for interacting with Google Cloud Storage:
- POST   /storage/public/upload  — Upload file to public bucket
- GET    /storage/public/{name}  — Get public URL for a file
- DELETE /storage/public/{name}  — Delete file from public bucket (admin only)

- POST   /storage/private/upload — Upload file to private bucket
- GET    /storage/private/{name} — Generate a time-limited signed URL
- DELETE /storage/private/{name} — Delete file from private bucket (admin only)
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, SuperUser
from app.core.logging import get_logger
from app.services.gcs_service import BucketType, gcs_service

logger = get_logger(__name__)
router = APIRouter(prefix="/storage", tags=["Storage"])


# =============================================================================
# Helper function
# =============================================================================

def _generate_unique_filename(original_filename: str | None) -> str:
    """Generate a unique filename using UUID to prevent collisions."""
    ext = ""
    if original_filename and "." in original_filename:
        ext = f".{original_filename.split('.')[-1]}"
    return f"{uuid.uuid4()}{ext}"


# =============================================================================
# Public Bucket Endpoints
# =============================================================================

@router.post(
    "/public/upload",
    response_model=dict[str, str],
    summary="Upload a file to the public bucket",
)
async def upload_public(
    file: Annotated[UploadFile, File(...)],
    current_user: CurrentUser,
) -> dict[str, str]:
    """
    Upload a file to the public GCS bucket.

    Files uploaded here are world-readable.
    Returns the public HTTPS URL of the uploaded file.
    """
    filename = _generate_unique_filename(file.filename)
    path = f"users/{current_user.id}/{filename}"

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"

    public_url = gcs_service.upload_public(content, path, content_type)

    return {"url": public_url, "path": path}


@router.get(
    "/public/{path:path}",
    response_model=dict[str, str],
    summary="Get public URL for a file",
)
async def get_public_url(path: str) -> dict[str, str]:
    """
    Get the public URL for a given GCS object path.

    This does not verify if the file exists. It just constructs the public URL.
    """
    return {"url": gcs_service.get_public_url(path)}


@router.delete(
    "/public/{path:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a file from the public bucket (admin only)",
)
async def delete_public(
    path: str,
    _: SuperUser,
) -> None:
    """Delete a file from the public bucket. Requires superuser privileges."""
    deleted = gcs_service.delete_file(BucketType.PUBLIC, path)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or already deleted",
        )


# =============================================================================
# Private Bucket Endpoints
# =============================================================================

@router.post(
    "/private/upload",
    response_model=dict[str, str],
    summary="Upload a file to the private bucket",
)
async def upload_private(
    file: Annotated[UploadFile, File(...)],
    current_user: CurrentUser,
) -> dict[str, str]:
    """
    Upload a file to the private GCS bucket.

    Files uploaded here are NOT publicly accessible.
    Returns the GCS object path (use GET /private/{path} to get a signed URL).
    """
    filename = _generate_unique_filename(file.filename)
    path = f"users/{current_user.id}/{filename}"

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"

    gcs_service.upload_private(content, path, content_type)

    return {"path": path}


@router.get(
    "/private/{path:path}",
    response_model=dict[str, str],
    summary="Generate a signed URL for a private file",
)
async def get_signed_url(
    path: str,
    current_user: CurrentUser,
    expires_in: int = 60,
) -> dict[str, str]:
    """
    Generate a V4 signed URL for a file in the private bucket.

    Provides time-limited download access (default 60 minutes) to the file
    without making it public.
    """
    # Basic authorization check: users can only access their own files
    # unless they are superusers. Assuming path format: users/{user_id}/...
    if not current_user.is_superuser and not path.startswith(f"users/{current_user.id}/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this file",
        )

    if not gcs_service.file_exists(BucketType.PRIVATE, path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    signed_url = gcs_service.generate_signed_url(path, expiration_minutes=expires_in)
    return {"signed_url": signed_url, "expires_in_minutes": expires_in}


@router.delete(
    "/private/{path:path}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a file from the private bucket (admin only)",
)
async def delete_private(
    path: str,
    _: SuperUser,
) -> None:
    """Delete a file from the private bucket. Requires superuser privileges."""
    deleted = gcs_service.delete_file(BucketType.PRIVATE, path)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or already deleted",
        )
