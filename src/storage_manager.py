"""
Unified Storage Manager — abstraction layer over storage providers.
Supports Google Cloud Storage, Digital Ocean Spaces, and Cloudflare R2.

The selection happens at startup via `Storage.PROVIDER` in config.yaml plus
the matching feature flag. DO and R2 are both S3-compatible (boto3) and share
most code paths; GCP uses google-cloud-storage and lives on its own branch.
"""

from pathlib import Path
from typing import Any, List, Dict, Optional, Tuple, Type
import datetime as dt
from zoneinfo import ZoneInfo

from logger import logger
from config.config import settings


# Provider identifiers — keep in sync with config.yaml `Storage.PROVIDER`.
PROVIDER_GCP = "GCP"
PROVIDER_DO = "DigitalOcean"
PROVIDER_R2 = "CloudflareR2"
S3_COMPAT_PROVIDERS = (PROVIDER_DO, PROVIDER_R2)


class StorageManager:
    """
    Unified storage manager that routes to the configured provider.
    """

    _instance = None
    _provider_instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_provider()
        return cls._instance

    def _initialize_provider(self):
        """Initialize the configured storage provider."""
        try:
            provider = settings.Storage.PROVIDER

            if provider == PROVIDER_R2 and settings.FeatureFlags.ENABLE_CLOUDFLARE_R2_STORAGE:
                logger.info("[STORAGE_MANAGER] Initializing Cloudflare R2 storage")
                from cloudflare.r2_storage import CloudflareR2StorageManager
                self._provider_instance = CloudflareR2StorageManager()
                self._provider_type = PROVIDER_R2
                self._buckets = {
                    'properties': settings.Cloudflare.R2.PROPERTIES_BUCKET,
                    'templates': settings.Cloudflare.R2.TEMPLATES_BUCKET,
                    'users': settings.Cloudflare.R2.USER_BUCKET,
                }

            elif provider == PROVIDER_DO and settings.FeatureFlags.ENABLE_DIGITAL_OCEAN_STORAGE:
                logger.info("[STORAGE_MANAGER] Initializing Digital Ocean Spaces storage")
                from digitalocean.ocean_storage import DigitalOceanStorageManager
                self._provider_instance = DigitalOceanStorageManager()
                self._provider_type = PROVIDER_DO
                self._buckets = {
                    'properties': settings.DigitalOcean.Spaces.PROPERTIES_BUCKET,
                    'templates': settings.DigitalOcean.Spaces.TEMPLATES_BUCKET,
                    'users': settings.DigitalOcean.Spaces.USER_BUCKET,
                }

            else:
                logger.info("[STORAGE_MANAGER] Initializing Google Cloud Storage (fallback)")
                from gcp.storage import StorageManager as GCPStorageManager
                self._provider_instance = GCPStorageManager()
                self._provider_type = PROVIDER_GCP
                self._buckets = {
                    'properties': settings.GCP.Storage.PROPERTIES_BUCKET,
                    'templates': settings.GCP.Storage.TEMPLATES_BUCKET,
                    'users': settings.GCP.Storage.USER_BUCKET,
                }

            logger.info(f"[STORAGE_MANAGER] Using {self._provider_type} storage provider")
            logger.info(f"[STORAGE_MANAGER] Bucket configuration: {self._buckets}")

        except Exception as e:
            logger.exception(f"Failed to initialize storage provider: {e}")
            raise e

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_s3_compat(self) -> bool:
        """True when active provider speaks the S3 API (DO or R2)."""
        return self._provider_type in S3_COMPAT_PROVIDERS

    def _s3_url_prefix(self) -> str:
        return "s3://"

    def _gcp_url_prefix(self) -> str:
        return "gs://"

    def _provider_url_prefix(self) -> str:
        return self._s3_url_prefix() if self._is_s3_compat() else self._gcp_url_prefix()

    def _get_s3_cloud_path_class(self) -> Type:
        """Return the CloudPath class matching the active S3-compat provider."""
        if self._provider_type == PROVIDER_R2:
            from cloudflare.storage_model import CloudPath
        else:
            from digitalocean.storage_model import CloudPath
        return CloudPath

    def _get_s3_adapter_class(self) -> Type:
        """Return the adapter class matching the active S3-compat provider."""
        if self._provider_type == PROVIDER_R2:
            from cloudflare.r2_storage import CloudflareR2StorageManager
            return CloudflareR2StorageManager
        from digitalocean.ocean_storage import DigitalOceanStorageManager
        return DigitalOceanStorageManager

    # ------------------------------------------------------------------
    # Read accessors
    # ------------------------------------------------------------------

    def get_client(self):
        """Get the underlying storage client"""
        return self._provider_instance.get_client()

    def get_provider_type(self) -> str:
        """Get the current storage provider type"""
        return self._provider_type

    def get_buckets(self) -> Dict[str, str]:
        """Get bucket configuration for current provider"""
        return self._buckets

    # ------------------------------------------------------------------
    # URL generation
    # ------------------------------------------------------------------

    def generate_signed_url_for_view(self, bucket: str, key: str) -> str:
        """Generate signed URL for viewing/downloading"""
        if self._is_s3_compat():
            return self._provider_instance.generate_signed_url_for_view(bucket, key)
        # GCP
        gcp_client = self._provider_instance.get_client()
        bucket_obj = gcp_client.bucket(bucket)
        blob = bucket_obj.blob(key)
        return self._provider_instance.generate_signed_url_for_view(blob)

    def generate_signed_url_for_upload(self, bucket: str, key: str, content_type: str) -> str:
        """Generate signed URL for uploading"""
        if self._is_s3_compat():
            return self._provider_instance.generate_signed_url_for_upload(bucket, key, content_type)
        # GCP
        gcp_client = self._provider_instance.get_client()
        bucket_obj = gcp_client.bucket(bucket)
        blob = bucket_obj.blob(key)
        return self._provider_instance.generate_signed_url_for_upload(blob, content_type)

    def generate_signed_url_from_url(self, storage_url: str, method='GET', content_type: str = None, send_file_name: bool = False):
        """Generate signed URL from storage URL (gs:// or s3://)"""
        if self._is_s3_compat():
            adapter = self._get_s3_adapter_class()
            return adapter.generate_signed_url_from_s3_url(storage_url, method, content_type, send_file_name)
        from gcp.storage import StorageManager as GCPStorageManager
        return GCPStorageManager.generate_signed_url_from_gs_url(storage_url, method, content_type, send_file_name)

    def parse_storage_url(self, storage_url: str) -> dict:
        """Parse storage URL to extract bucket and key/path"""
        if self._is_s3_compat():
            adapter = self._get_s3_adapter_class()
            return adapter.parse_s3_url(storage_url)
        from gcp.storage import StorageManager as GCPStorageManager
        return GCPStorageManager.parse_gs_url(storage_url)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def save_blob(self, source_file: Path, bucket: str, key: str):
        """Save a single file to storage"""
        if self._is_s3_compat():
            CloudPath = self._get_s3_cloud_path_class()
            cloud_path = CloudPath(bucket_id=bucket, path=Path(key))
            self._get_s3_adapter_class().save_blob(source_file, cloud_path)
        else:
            from gcp.storage_model import CloudPath
            from gcp.storage import StorageManager as GCPStorageManager
            cloud_path = CloudPath(bucket_id=bucket, path=Path(key))
            GCPStorageManager.save_blob(source_file, cloud_path)

    def save_blobs(self, source_dir: Path, bucket: str, prefix: str):
        """Save multiple files from directory to storage"""
        if self._is_s3_compat():
            CloudPath = self._get_s3_cloud_path_class()
            cloud_path = CloudPath(bucket_id=bucket, path=Path(prefix))
            self._get_s3_adapter_class().save_blobs(source_dir, cloud_path)
        else:
            from gcp.storage_model import CloudPath
            from gcp.storage import StorageManager as GCPStorageManager
            cloud_path = CloudPath(bucket_id=bucket, path=Path(prefix))
            GCPStorageManager.save_blobs(source_dir, cloud_path)

    def load_blob(self, bucket: str, key: str, dest_file: Path):
        """Download a single file from storage"""
        if self._is_s3_compat():
            CloudPath = self._get_s3_cloud_path_class()
            cloud_path = CloudPath(bucket_id=bucket, path=Path(key))
            self._get_s3_adapter_class().load_blob(cloud_path, dest_file)
        else:
            from gcp.storage_model import CloudPath
            from gcp.storage import StorageManager as GCPStorageManager
            cloud_path = CloudPath(bucket_id=bucket, path=Path(key))
            GCPStorageManager.load_blob(cloud_path, dest_file)

    def download_blob_to_file(self, storage_url: str, local_file_path: str):
        """Download file from storage URL to local path"""
        if self._is_s3_compat():
            self._get_s3_adapter_class().download_blob_to_file(storage_url, local_file_path)
        else:
            from gcp.storage import StorageManager as GCPStorageManager
            GCPStorageManager.download_blob_to_file(storage_url, local_file_path)

    def list_objects(self, bucket: str, prefix: str = "") -> List[dict]:
        """List objects in bucket with prefix"""
        if self._is_s3_compat():
            return self._provider_instance.list_objects(bucket, prefix)

        # GCP path: emulate the S3 list shape
        from gcp.storage_model import CloudPath
        from gcp.storage import StorageManager as GCPStorageManager
        cloud_path = CloudPath(bucket_id=bucket, path=Path(prefix))
        blob_paths = GCPStorageManager.list_blobs_in_path(cloud_path)
        objects = []
        for blob_path in blob_paths:
            parsed = GCPStorageManager.parse_gs_url(blob_path)
            objects.append({
                'Key': parsed['file_name'],
                'Size': 0,
                'LastModified': None,
                'StorageUrl': blob_path,
            })
        return objects

    def object_exists(self, bucket: str, key: str) -> bool:
        """Check if object exists in storage"""
        if self._is_s3_compat():
            return self._provider_instance.object_exists(bucket, key)
        gcp_client = self._provider_instance.get_client()
        bucket_obj = gcp_client.bucket(bucket)
        blob = bucket_obj.blob(key)
        return blob.exists()

    def delete_object(self, bucket: str, key: str):
        """Delete object from storage"""
        if self._is_s3_compat():
            self._provider_instance.delete_object(bucket, key)
        else:
            gcp_client = self._provider_instance.get_client()
            bucket_obj = gcp_client.bucket(bucket)
            blob = bucket_obj.blob(key)
            blob.delete()

    # ------------------------------------------------------------------
    # Project-specific helpers (URL prefix differs per provider)
    # ------------------------------------------------------------------

    def get_image_repos_for_project(self, user_id: str, project_id: str) -> List[str]:
        """Get image storage paths for a project"""
        try:
            from utils.session_utils import get_session_refs_by_ids
            _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)

            project_doc = project_ref.get()
            if not project_doc.exists:
                logger.error(f"Unable to fetch project for user '{user_id}' and project '{project_id}'")
                return []

            property_id = project_doc.to_dict().get("property_id", None)
            prefix = self._provider_url_prefix()

            image_repos = []
            if property_id:
                image_repos.append(f"{prefix}{self._buckets['properties']}/{property_id}/Images")

            image_repos.append(f"{prefix}{self._buckets['users']}/{user_id}/{project_id}/images")
            return image_repos

        except Exception as e:
            logger.exception(f"Failed to get image repos for project {project_id}: {e}")
            return []

    def get_video_repos_for_project(self, user_id: str, project_id: str) -> List[str]:
        """Get video storage paths for a project"""
        try:
            prefix = self._provider_url_prefix()
            return [
                f"{prefix}{self._buckets['users']}/{user_id}/{project_id}/videos",
                f"{prefix}{self._buckets['users']}/{user_id}/{project_id}/scene_clips",
            ]
        except Exception as e:
            logger.exception(f"Failed to get video repos for project {project_id}: {e}")
            return []

    def gen_signed_urls_for_bucket(self, storage_location: str, excluded_urls: List[str] = [],
                                  file_types: List[str] = None):
        """Generate signed URLs for files in a storage location"""
        try:
            parsed = self.parse_storage_url(storage_location)
            bucket = parsed["bucket_name"]
            prefix = parsed["file_name"]

            objects = self.list_objects(bucket, prefix)
            signed_urls = []

            if file_types is None:
                file_types = ['.jpg', '.jpeg', '.png', '.webp', '.avif', '.mp4', '.mov', '.webm', '.m4v']

            current_time = dt.datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
            expiry_delta = dt.timedelta(hours=settings.Authentication.SignedURL.GET_EXPIRY_IN_HOURS)
            signature_expiry = current_time + expiry_delta

            url_prefix = self._provider_url_prefix()
            for obj in objects:
                key = obj['Key']
                obj_url = f"{url_prefix}{bucket}/{key}"

                if obj_url in excluded_urls:
                    continue
                if file_types and not any(key.lower().endswith(ext) for ext in file_types):
                    continue

                signed_url = self.generate_signed_url_for_view(bucket, key)
                signed_urls.append({
                    "file_name": key,
                    "signed_url": signed_url,
                    "storage_url": obj_url,
                })

            return signed_urls, signature_expiry

        except Exception as e:
            logger.exception(f"Failed to generate signed URLs for {storage_location}: {e}")
            return [], None


# Create the unified storage manager instance
storage_manager = StorageManager()

# For backward compatibility, also create the client
cloud_storage_client = storage_manager.get_client()
