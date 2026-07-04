"""MinIO file storage."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.config import settings


class MinioStore:
    def __init__(self) -> None:
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self.bucket = settings.minio_bucket
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            if not self.client.bucket_exists(self.bucket):
                self.client.make_bucket(self.bucket)
        except S3Error:
            pass

    def upload_file(self, local_path: Path, object_name: str) -> str:
        self.client.fput_object(self.bucket, object_name, str(local_path))
        return f"{self.bucket}/{object_name}"

    def upload_bytes(self, data: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            self.bucket,
            object_name,
            BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return f"{self.bucket}/{object_name}"

    def is_available(self) -> bool:
        try:
            self.client.bucket_exists(self.bucket)
            return True
        except Exception:
            return False
