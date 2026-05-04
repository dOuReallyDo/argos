"""File storage backends — local filesystem and S3/MinIO."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO, Optional

import boto3
from minio import Minio

from core.config import get_settings
from core.logging import logger

settings = get_settings()


class StorageBackend:
    """Abstract storage backend with pluggable implementations."""

    async def store(
        self, file_path: Path, doc_id: str, filename: str
    ) -> str:
        """Store a file, return its storage path/URL."""
        raise NotImplementedError

    async def retrieve(self, storage_path: str) -> bytes:
        """Retrieve file bytes by storage path."""
        raise NotImplementedError

    async def delete(self, storage_path: str) -> None:
        """Delete a file from storage."""
        raise NotImplementedError


class LocalStorage(StorageBackend):
    """Store files on the local filesystem."""

    def __init__(self):
        self._base = Path(settings.storage_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def _path_for(self, doc_id: str, filename: str) -> Path:
        # Organize: docs/{date}/{doc_id}/{filename}
        from datetime import date

        today = date.today().isoformat()
        dir_path = self._base / today / doc_id
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path / filename

    async def store(
        self, file_path: Path, doc_id: str, filename: str
    ) -> str:
        dest = self._path_for(doc_id, filename)
        shutil.copy2(str(file_path), str(dest))
        logger.debug(f"Stored locally: {dest}")
        return str(dest)

    async def retrieve(self, storage_path: str) -> bytes:
        path = Path(storage_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {storage_path}")
        return path.read_bytes()

    async def delete(self, storage_path: str) -> None:
        path = Path(storage_path)
        if path.exists():
            path.unlink()
            logger.debug(f"Deleted: {storage_path}")


class S3Storage(StorageBackend):
    """Store files on S3 or MinIO (S3-compatible)."""

    def __init__(self):
        self._bucket = settings.s3_bucket
        self._endpoint = settings.s3_endpoint

        if self._endpoint:
            # MinIO or custom S3-compatible
            self._client = Minio(
                endpoint=self._endpoint.replace("http://", "").replace("https://", ""),
                access_key=settings.s3_access_key,
                secret_key=settings.s3_secret_key,
                secure=self._endpoint.startswith("https"),
            )
            self._is_minio = True
        else:
            # AWS S3
            self._client = boto3.client(
                "s3",
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region,
            )
            self._is_minio = False

        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if self._is_minio:
                if not self._client.bucket_exists(self._bucket):
                    self._client.make_bucket(self._bucket)
            else:
                self._client.head_bucket(Bucket=self._bucket)
        except Exception:
            if not self._is_minio:
                self._client.create_bucket(
                    Bucket=self._bucket,
                    CreateBucketConfiguration={
                        "LocationConstraint": settings.s3_region
                    },
                )

    def _object_key(self, doc_id: str, filename: str) -> str:
        from datetime import date

        today = date.today().isoformat()
        return f"documents/{today}/{doc_id}/{filename}"

    async def store(
        self, file_path: Path, doc_id: str, filename: str
    ) -> str:
        key = self._object_key(doc_id, filename)

        if self._is_minio:
            self._client.fput_object(
                self._bucket, key, str(file_path)
            )
        else:
            self._client.upload_file(
                str(file_path), self._bucket, key
            )

        path = f"s3://{self._bucket}/{key}"
        logger.debug(f"Stored on S3: {path}")
        return path

    async def retrieve(self, storage_path: str) -> bytes:
        # Parse s3://bucket/key
        parts = storage_path.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        key = parts[1]

        if self._is_minio:
            response = self._client.get_object(bucket, key)
            return response.read()
        else:
            response = self._client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read()

    async def delete(self, storage_path: str) -> None:
        parts = storage_path.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        key = parts[1]

        if self._is_minio:
            self._client.remove_object(bucket, key)
        else:
            self._client.delete_object(Bucket=bucket, Key=key)

        logger.debug(f"Deleted from S3: {storage_path}")
