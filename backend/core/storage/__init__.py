"""
Storage layer for MinIO/S3
"""
from .minio_client import MinIOClient, minio_client

__all__ = ["MinIOClient", "minio_client"]
