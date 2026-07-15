"""MinIO / S3-compatible storage adapter.

Implements the StorageProvider protocol using aioboto3.
All operations are async. The client is created once and shared.
"""

import logging
from typing import Any

import aioboto3
from botocore.exceptions import ClientError

from fetch.config import get_settings
from fetch.domain.protocols import UploadResult

logger = logging.getLogger(__name__)


class MinioStorageProvider:
    """S3-compatible object storage backed by MinIO (or AWS S3)."""

    def __init__(self) -> None:
        settings = get_settings().object_storage
        self._session = aioboto3.Session()
        self._endpoint = settings.endpoint
        self._access_key = settings.access_key
        self._secret_key = settings.secret_key
        self._bucket = settings.bucket
        self._region = settings.region

    def _client(self) -> Any:
        """Return an async S3 client context manager."""
        return self._session.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
        )

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: str,
    ) -> UploadResult:
        """Upload bytes to the given key. Overwrites if key already exists."""
        async with self._client() as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        logger.info(
            "storage_upload_complete",
            extra={"key": key, "size_bytes": len(data), "bucket": self._bucket},
        )
        return UploadResult(
            key=key,
            url=f"{self._endpoint}/{self._bucket}/{key}",
            size_bytes=len(data),
        )

    async def download(self, key: str) -> bytes:
        """Download object at key. Raises KeyError if not found."""
        async with self._client() as s3:
            try:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                return await response["Body"].read()
            except ClientError as exc:
                if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                    raise KeyError(f"Object not found: {key}") from exc
                raise

    async def delete(self, key: str) -> None:
        """Delete object at key. No-op if key does not exist."""
        async with self._client() as s3:
            await s3.delete_object(Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        """Return True if the key exists in the bucket."""
        async with self._client() as s3:
            try:
                await s3.head_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError as exc:
                if exc.response["Error"]["Code"] in ("NoSuchKey", "404", "403"):
                    return False
                raise

    async def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist. Used in tests and local setup."""
        async with self._client() as s3:
            try:
                await s3.head_bucket(Bucket=self._bucket)
            except ClientError:
                await s3.create_bucket(Bucket=self._bucket)
                logger.info("storage_bucket_created", extra={"bucket": self._bucket})
