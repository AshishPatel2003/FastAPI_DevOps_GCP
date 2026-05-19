"""
GCP Cloud Storage Service.

Handles public and private GCS bucket operations:
- Public bucket: files are world-readable (website images, static assets)
- Private bucket: files require V4 signed URLs for time-limited access

On Cloud Run, authentication uses the service account attached to the instance
(Application Default Credentials). No explicit credential configuration needed.

For local development, set GOOGLE_APPLICATION_CREDENTIALS to a service account
JSON key file path.
"""

import datetime
import io
from enum import Enum
from typing import BinaryIO

from google.cloud import storage  # type: ignore[import-untyped]
from google.cloud.storage import Blob, Bucket

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class BucketType(str, Enum):
    """Enum to distinguish between public and private GCS buckets."""
    PUBLIC = "public"
    PRIVATE = "private"


class GCSService:
    """
    Google Cloud Storage service for public and private file management.

    Usage:
        gcs = GCSService()

        # Public upload
        url = await gcs.upload_public(file_bytes, "images/logo.png", "image/png")

        # Private upload + signed URL
        await gcs.upload_private(file_bytes, "contracts/doc.pdf", "application/pdf")
        signed = await gcs.generate_signed_url("contracts/doc.pdf")

        # Delete
        await gcs.delete_file(BucketType.PUBLIC, "images/logo.png")
    """

    def __init__(self) -> None:
        # The Storage client uses ADC (Application Default Credentials)
        # On Cloud Run: uses the attached service account automatically
        # Local: uses GOOGLE_APPLICATION_CREDENTIALS env var
        self._client = storage.Client(project=settings.GCP_PROJECT_ID or None)
        self._public_bucket: Bucket = self._client.bucket(settings.GCS_PUBLIC_BUCKET)
        self._private_bucket: Bucket = self._client.bucket(settings.GCS_PRIVATE_BUCKET)

    def _get_bucket(self, bucket_type: BucketType) -> Bucket:
        return self._public_bucket if bucket_type == BucketType.PUBLIC else self._private_bucket

    # ------------------------------------------------------------------
    # Public Bucket Operations
    # ------------------------------------------------------------------

    def upload_public(
        self,
        file_data: bytes | BinaryIO,
        destination_path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload a file to the public bucket and return its public URL.

        The file is made world-readable by setting the predefined ACL to
        'publicRead'. The public bucket should also have uniform bucket-level
        access disabled for ACLs to work (or use IAM allUsers binding instead).

        Args:
            file_data: File bytes or file-like object.
            destination_path: GCS object path (e.g., "images/photo.jpg").
            content_type: MIME type of the file.

        Returns:
            Public HTTPS URL of the uploaded file.
        """
        blob: Blob = self._public_bucket.blob(destination_path)
        blob.content_type = content_type

        if isinstance(file_data, bytes):
            blob.upload_from_string(file_data, content_type=content_type)
        else:
            blob.upload_from_file(file_data, content_type=content_type)

        # Make the blob publicly accessible
        blob.make_public()

        public_url = blob.public_url
        logger.info(
            "File uploaded to public bucket",
            extra={
                "bucket": settings.GCS_PUBLIC_BUCKET,
                "path": destination_path,
                "url": public_url,
            },
        )
        return public_url

    def get_public_url(self, destination_path: str) -> str:
        """
        Get the public URL for an existing file in the public bucket.

        Args:
            destination_path: GCS object path.

        Returns:
            Public HTTPS URL.
        """
        blob = self._public_bucket.blob(destination_path)
        return blob.public_url

    # ------------------------------------------------------------------
    # Private Bucket Operations
    # ------------------------------------------------------------------

    def upload_private(
        self,
        file_data: bytes | BinaryIO,
        destination_path: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Upload a file to the private bucket (no public access).

        Args:
            file_data: File bytes or file-like object.
            destination_path: GCS object path.
            content_type: MIME type of the file.

        Returns:
            The GCS object path (use generate_signed_url for access).
        """
        blob: Blob = self._private_bucket.blob(destination_path)
        blob.content_type = content_type

        if isinstance(file_data, bytes):
            blob.upload_from_string(file_data, content_type=content_type)
        else:
            blob.upload_from_file(file_data, content_type=content_type)

        logger.info(
            "File uploaded to private bucket",
            extra={
                "bucket": settings.GCS_PRIVATE_BUCKET,
                "path": destination_path,
            },
        )
        return destination_path

    def generate_signed_url(
        self,
        destination_path: str,
        expiration_minutes: int | None = None,
        method: str = "GET",
    ) -> str:
        """
        Generate a V4 signed URL for temporary private file access.

        Signed URLs grant time-limited access without requiring authentication.
        They can be shared with external users for secure, temporary downloads.

        Args:
            destination_path: GCS object path in the private bucket.
            expiration_minutes: URL validity duration (defaults to settings value).
            method: HTTP method — "GET" for download, "PUT" for upload.

        Returns:
            Time-limited signed HTTPS URL.
        """
        expiry = expiration_minutes or settings.GCS_SIGNED_URL_EXPIRATION_MINUTES
        blob: Blob = self._private_bucket.blob(destination_path)

        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=expiry),
            method=method,
        )
        logger.info(
            "Signed URL generated",
            extra={
                "bucket": settings.GCS_PRIVATE_BUCKET,
                "path": destination_path,
                "expires_in_minutes": expiry,
            },
        )
        return signed_url

    def get_file(self, bucket_type: BucketType, destination_path: str) -> bytes:
        """
        Download file content as bytes from either bucket.

        Args:
            bucket_type: PUBLIC or PRIVATE bucket.
            destination_path: GCS object path.

        Returns:
            File content as bytes.

        Raises:
            google.cloud.exceptions.NotFound: If the file does not exist.
        """
        bucket = self._get_bucket(bucket_type)
        blob = bucket.blob(destination_path)
        content = blob.download_as_bytes()
        logger.debug(
            "File downloaded",
            extra={"bucket_type": bucket_type, "path": destination_path},
        )
        return content

    def delete_file(self, bucket_type: BucketType, destination_path: str) -> bool:
        """
        Delete a file from either bucket.

        Args:
            bucket_type: PUBLIC or PRIVATE bucket.
            destination_path: GCS object path.

        Returns:
            True if deleted, False if file was not found.
        """
        bucket = self._get_bucket(bucket_type)
        blob = bucket.blob(destination_path)

        try:
            blob.delete()
            logger.info(
                "File deleted from GCS",
                extra={"bucket_type": bucket_type, "path": destination_path},
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "GCS delete failed (file may not exist)",
                extra={"path": destination_path, "error": str(exc)},
            )
            return False

    def file_exists(self, bucket_type: BucketType, destination_path: str) -> bool:
        """Check if a file exists in the specified bucket."""
        bucket = self._get_bucket(bucket_type)
        blob = bucket.blob(destination_path)
        return blob.exists()

    def list_files(
        self,
        bucket_type: BucketType,
        prefix: str = "",
        max_results: int = 100,
    ) -> list[str]:
        """
        List file paths in a bucket with optional prefix filtering.

        Args:
            bucket_type: PUBLIC or PRIVATE bucket.
            prefix: Filter files by path prefix (e.g., "images/").
            max_results: Maximum number of results to return.

        Returns:
            List of GCS object paths.
        """
        bucket = self._get_bucket(bucket_type)
        blobs = self._client.list_blobs(bucket, prefix=prefix, max_results=max_results)
        return [blob.name for blob in blobs]


# Module-level singleton
gcs_service = GCSService()
