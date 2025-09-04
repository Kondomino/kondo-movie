"""
Unified Storage Manager - Provides abstraction layer for different storage providers
Supports both Google Cloud Storage and Digital Ocean Spaces
"""

from pathlib import Path
from typing import Any, List, Dict, Optional
import datetime as dt
from zoneinfo import ZoneInfo

from logger import logger
from config.config import settings


class StorageManager:
    """
    Unified storage manager that routes to appropriate storage provider
    based on configuration settings
    """
    
    _instance = None
    _provider_instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize_provider()
        return cls._instance
    
    def _initialize_provider(self):
        """Initialize the appropriate storage provider based on configuration"""
        try:
            provider = settings.Storage.PROVIDER
            
            if provider == "DigitalOcean" and settings.FeatureFlags.ENABLE_DIGITAL_OCEAN_STORAGE:
                logger.info("[STORAGE_MANAGER] Initializing Digital Ocean Spaces storage")
                from digitalocean.ocean_storage import DigitalOceanStorageManager
                self._provider_instance = DigitalOceanStorageManager()
                self._provider_type = "DigitalOcean"
                
                # Set bucket configuration for Digital Ocean
                self._buckets = {
                    'properties': settings.DigitalOcean.Spaces.PROPERTIES_BUCKET,
                    'templates': settings.DigitalOcean.Spaces.TEMPLATES_BUCKET,
                    'users': settings.DigitalOcean.Spaces.USER_BUCKET,
                }
                
            else:
                logger.info("[STORAGE_MANAGER] Initializing Google Cloud Storage (fallback)")
                from gcp.storage import StorageManager as GCPStorageManager
                self._provider_instance = GCPStorageManager()
                self._provider_type = "GCP"
                
                # Set bucket configuration for GCP
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
    
    def get_client(self):
        """Get the underlying storage client"""
        return self._provider_instance.get_client()
    
    def get_provider_type(self) -> str:
        """Get the current storage provider type"""
        return self._provider_type
    
    def get_buckets(self) -> Dict[str, str]:
        """Get bucket configuration for current provider"""
        return self._buckets
    
    # URL Generation Methods
    
    def generate_signed_url_for_view(self, bucket: str, key: str) -> str:
        """Generate signed URL for viewing/downloading"""
        if self._provider_type == "DigitalOcean":
            return self._provider_instance.generate_signed_url_for_view(bucket, key)
        else:
            # For GCP, we need to get the blob first
            from google.cloud.storage import Blob
            gcp_client = self._provider_instance.get_client()
            bucket_obj = gcp_client.bucket(bucket)
            blob = bucket_obj.blob(key)
            return self._provider_instance.generate_signed_url_for_view(blob)
    
    def generate_signed_url_for_upload(self, bucket: str, key: str, content_type: str) -> str:
        """Generate signed URL for uploading"""
        if self._provider_type == "DigitalOcean":
            return self._provider_instance.generate_signed_url_for_upload(bucket, key, content_type)
        else:
            # For GCP, we need to get the blob first
            from google.cloud.storage import Blob
            gcp_client = self._provider_instance.get_client()
            bucket_obj = gcp_client.bucket(bucket)
            blob = bucket_obj.blob(key)
            return self._provider_instance.generate_signed_url_for_upload(blob, content_type)
    
    def generate_signed_url_from_url(self, storage_url: str, method='GET', content_type: str = None, send_file_name: bool = False):
        """Generate signed URL from storage URL (gs:// or s3://)"""
        if self._provider_type == "DigitalOcean":
            from digitalocean.ocean_storage import DigitalOceanStorageManager
            return DigitalOceanStorageManager.generate_signed_url_from_s3_url(
                storage_url, method, content_type, send_file_name
            )
        else:
            from gcp.storage import StorageManager as GCPStorageManager
            return GCPStorageManager.generate_signed_url_from_gs_url(
                storage_url, method, content_type, send_file_name
            )
    
    def parse_storage_url(self, storage_url: str) -> dict:
        """Parse storage URL to extract bucket and key/path"""
        if self._provider_type == "DigitalOcean":
            from digitalocean.ocean_storage import DigitalOceanStorageManager
            return DigitalOceanStorageManager.parse_s3_url(storage_url)
        else:
            from gcp.storage import StorageManager as GCPStorageManager
            return GCPStorageManager.parse_gs_url(storage_url)
    
    # File Operations
    
    def save_blob(self, source_file: Path, bucket: str, key: str):
        """Save a single file to storage"""
        if self._provider_type == "DigitalOcean":
            from digitalocean.storage_model import CloudPath
            cloud_path = CloudPath(bucket_id=bucket, path=Path(key))
            from digitalocean.ocean_storage import DigitalOceanStorageManager
            DigitalOceanStorageManager.save_blob(source_file, cloud_path)
        else:
            from gcp.storage_model import CloudPath
            cloud_path = CloudPath(bucket_id=bucket, path=Path(key))
            from gcp.storage import StorageManager as GCPStorageManager
            GCPStorageManager.save_blob(source_file, cloud_path)
    
    def save_blobs(self, source_dir: Path, bucket: str, prefix: str):
        """Save multiple files from directory to storage"""
        if self._provider_type == "DigitalOcean":
            from digitalocean.storage_model import CloudPath
            cloud_path = CloudPath(bucket_id=bucket, path=Path(prefix))
            from digitalocean.ocean_storage import DigitalOceanStorageManager
            DigitalOceanStorageManager.save_blobs(source_dir, cloud_path)
        else:
            from gcp.storage_model import CloudPath
            cloud_path = CloudPath(bucket_id=bucket, path=Path(prefix))
            from gcp.storage import StorageManager as GCPStorageManager
            GCPStorageManager.save_blobs(source_dir, cloud_path)
    
    def load_blob(self, bucket: str, key: str, dest_file: Path):
        """Download a single file from storage"""
        if self._provider_type == "DigitalOcean":
            from digitalocean.storage_model import CloudPath
            cloud_path = CloudPath(bucket_id=bucket, path=Path(key))
            from digitalocean.ocean_storage import DigitalOceanStorageManager
            DigitalOceanStorageManager.load_blob(cloud_path, dest_file)
        else:
            from gcp.storage_model import CloudPath
            cloud_path = CloudPath(bucket_id=bucket, path=Path(key))
            from gcp.storage import StorageManager as GCPStorageManager
            GCPStorageManager.load_blob(cloud_path, dest_file)
    
    def download_blob_to_file(self, storage_url: str, local_file_path: str):
        """Download file from storage URL to local path"""
        if self._provider_type == "DigitalOcean":
            from digitalocean.ocean_storage import DigitalOceanStorageManager
            DigitalOceanStorageManager.download_blob_to_file(storage_url, local_file_path)
        else:
            from gcp.storage import StorageManager as GCPStorageManager
            GCPStorageManager.download_blob_to_file(storage_url, local_file_path)
    
    def list_objects(self, bucket: str, prefix: str = "") -> List[dict]:
        """List objects in bucket with prefix"""
        if self._provider_type == "DigitalOcean":
            return self._provider_instance.list_objects(bucket, prefix)
        else:
            # For GCP, we need to implement this using the existing methods
            from gcp.storage_model import CloudPath
            cloud_path = CloudPath(bucket_id=bucket, path=Path(prefix))
            from gcp.storage import StorageManager as GCPStorageManager
            blob_paths = GCPStorageManager.list_blobs_in_path(cloud_path)
            
            # Convert to consistent format
            objects = []
            for blob_path in blob_paths:
                parsed = GCPStorageManager.parse_gs_url(blob_path)
                objects.append({
                    'Key': parsed['file_name'],
                    'Size': 0,  # GCP method doesn't provide size
                    'LastModified': None,  # GCP method doesn't provide timestamp
                    'StorageUrl': blob_path
                })
            return objects
    
    def object_exists(self, bucket: str, key: str) -> bool:
        """Check if object exists in storage"""
        if self._provider_type == "DigitalOcean":
            return self._provider_instance.object_exists(bucket, key)
        else:
            # For GCP, check using blob existence
            gcp_client = self._provider_instance.get_client()
            bucket_obj = gcp_client.bucket(bucket)
            blob = bucket_obj.blob(key)
            return blob.exists()
    
    def delete_object(self, bucket: str, key: str):
        """Delete object from storage"""
        if self._provider_type == "DigitalOcean":
            self._provider_instance.delete_object(bucket, key)
        else:
            # For GCP, delete using blob
            gcp_client = self._provider_instance.get_client()
            bucket_obj = gcp_client.bucket(bucket)
            blob = bucket_obj.blob(key)
            blob.delete()
    
    # Project-specific helper methods (maintaining compatibility with existing code)
    
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
            
            image_repos = []
            if property_id:
                # Property images path
                if self._provider_type == "DigitalOcean":
                    property_path = f"s3://{self._buckets['properties']}/{property_id}/Images"
                else:
                    property_path = f"gs://{self._buckets['properties']}/{property_id}/Images"
                image_repos.append(property_path)
            
            # Project images path
            if self._provider_type == "DigitalOcean":
                project_path = f"s3://{self._buckets['users']}/{user_id}/{project_id}/images"
            else:
                project_path = f"gs://{self._buckets['users']}/{user_id}/{project_id}/images"
            image_repos.append(project_path)
            
            return image_repos
            
        except Exception as e:
            logger.exception(f"Failed to get image repos for project {project_id}: {e}")
            return []
    
    def get_video_repos_for_project(self, user_id: str, project_id: str) -> List[str]:
        """Get video storage paths for a project"""
        try:
            video_repos = []
            
            # Raw videos path
            if self._provider_type == "DigitalOcean":
                videos_path = f"s3://{self._buckets['users']}/{user_id}/{project_id}/videos"
                scene_clips_path = f"s3://{self._buckets['users']}/{user_id}/{project_id}/scene_clips"
            else:
                videos_path = f"gs://{self._buckets['users']}/{user_id}/{project_id}/videos"
                scene_clips_path = f"gs://{self._buckets['users']}/{user_id}/{project_id}/scene_clips"
            
            video_repos.append(videos_path)
            video_repos.append(scene_clips_path)
            
            return video_repos
            
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
            
            # Default file types if not specified
            if file_types is None:
                file_types = ['.jpg', '.jpeg', '.png', '.webp', '.avif', '.mp4', '.mov', '.webm', '.m4v']
            
            current_time = dt.datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
            expiry_delta = dt.timedelta(hours=settings.Authentication.SignedURL.GET_EXPIRY_IN_HOURS)
            signature_expiry = current_time + expiry_delta
            
            for obj in objects:
                key = obj['Key']
                
                # Skip excluded files
                if self._provider_type == "DigitalOcean":
                    obj_url = f"s3://{bucket}/{key}"
                else:
                    obj_url = f"gs://{bucket}/{key}"
                    
                if obj_url in excluded_urls:
                    continue
                
                # Skip files that don't match specified file types
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
