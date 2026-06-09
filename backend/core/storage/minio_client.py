"""
MinIO Storage Client

Handles uploading scraped data to MinIO/S3 storage.
Generates signed URLs for data retrieval.
"""
import json
import logging
from datetime import timedelta
from typing import Dict, Any, Optional
from minio import Minio
from minio.error import S3Error
from io import BytesIO

from core.config import settings

logger = logging.getLogger(__name__)


class MinIOClient:
    """
    MinIO client for storing and retrieving scraped data

    Features:
    - Upload JSON data from scraper runs
    - Generate signed URLs for data access
    - Delete old data files
    - Bucket management
    """

    def __init__(self):
        """Initialize MinIO client with configuration from settings"""
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
        self.bucket_name = settings.MINIO_BUCKET
        self.internal_endpoint = settings.MINIO_ENDPOINT
        self.external_endpoint = settings.MINIO_EXTERNAL_ENDPOINT

        # Ensure bucket exists
        self._ensure_bucket_exists()

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"[MINIO] Created bucket: {self.bucket_name}")
            else:
                logger.debug(f"[MINIO] Bucket already exists: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"[MINIO] Error ensuring bucket exists: {e}")
            raise

    def upload_json(
        self,
        run_id: str,
        data: list,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Upload scraped data as JSON file to MinIO

        Args:
            run_id: Unique identifier for the scraping run
            data: List of scraped records (dict objects)
            metadata: Optional metadata to include in object headers

        Returns:
            Object name/path in MinIO bucket

        Raises:
            S3Error: If upload fails
        """
        object_name = f"runs/{run_id}.json"

        try:
            # Convert data to JSON bytes
            json_data = json.dumps(data, indent=2, ensure_ascii=False)
            json_bytes = json_data.encode('utf-8')
            json_stream = BytesIO(json_bytes)

            # Prepare metadata
            upload_metadata = {
                "Content-Type": "application/json",
                "run_id": str(run_id),
                "record_count": str(len(data))
            }

            if metadata:
                upload_metadata.update({
                    f"x-amz-meta-{k}": str(v) for k, v in metadata.items()
                })

            # Upload to MinIO
            result = self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=json_stream,
                length=len(json_bytes),
                content_type="application/json",
                metadata=upload_metadata
            )

            logger.info(f"[MINIO] Uploaded {len(data)} records to {object_name} "
                       f"(etag: {result.etag})")

            return object_name

        except S3Error as e:
            logger.error(f"[MINIO] Upload failed for run {run_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"[MINIO] Unexpected error during upload: {e}")
            raise

    def get_file_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(days=7)
    ) -> str:
        """
        Generate presigned URL for accessing a file

        Args:
            object_name: Object path in MinIO bucket
            expires: URL expiration time (default: 7 days)

        Returns:
            Presigned URL string with external endpoint (accessible from browser)
        """
        try:
            url = self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                expires=expires
            )

            # Replace internal endpoint with external endpoint for browser access
            if self.internal_endpoint != self.external_endpoint:
                url = url.replace(self.internal_endpoint, self.external_endpoint)
                logger.debug(f"[MINIO] Replaced internal endpoint with external: {self.external_endpoint}")

            logger.debug(f"[MINIO] Generated presigned URL for {object_name}")
            return url

        except S3Error as e:
            logger.error(f"[MINIO] Failed to generate URL for {object_name}: {e}")
            raise

    def get_public_url(self, object_name: str) -> str:
        """
        Get public URL for an object (MinIO endpoint + bucket + object)

        Note: This URL only works if bucket has public read policy.
        For private buckets, use get_file_url() instead.

        Args:
            object_name: Object path in MinIO bucket

        Returns:
            Public URL string
        """
        protocol = "https" if settings.MINIO_SECURE else "http"
        return f"{protocol}://{settings.MINIO_ENDPOINT}/{self.bucket_name}/{object_name}"

    def delete_file(self, object_name: str) -> bool:
        """
        Delete a file from MinIO

        Args:
            object_name: Object path in MinIO bucket

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )

            logger.info(f"[MINIO] Deleted object: {object_name}")
            return True

        except S3Error as e:
            logger.error(f"[MINIO] Failed to delete {object_name}: {e}")
            return False

    def file_exists(self, object_name: str) -> bool:
        """
        Check if a file exists in MinIO

        Args:
            object_name: Object path in MinIO bucket

        Returns:
            True if file exists, False otherwise
        """
        try:
            self.client.stat_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            return True
        except S3Error:
            return False

    def get_file_size(self, object_name: str) -> Optional[int]:
        """
        Get file size in bytes

        Args:
            object_name: Object path in MinIO bucket

        Returns:
            File size in bytes, or None if file doesn't exist
        """
        try:
            stat = self.client.stat_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            return stat.size
        except S3Error:
            return None


# Global MinIO client instance
minio_client = MinIOClient()
