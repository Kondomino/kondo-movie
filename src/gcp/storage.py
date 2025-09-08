from pathlib import Path
import argparse
import os
import datetime as dt
from zoneinfo import ZoneInfo
from typing import Any

from google.cloud import storage
from google import auth
from google.auth.transport import requests
from google.cloud.storage import transfer_manager, Blob
from google.oauth2 import service_account

from logger import logger
from config.config import settings
from gcp.storage_model import CloudPath
from utils.session_utils import get_session_refs_by_ids

STORAGE_SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-f0da3484f1a0.json'

class StorageManager():

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.setup()
        return cls._instance

    def setup(self):
        try:
            if os.path.exists(STORAGE_SERVICE_ACCOUNT_KEY_FILE_PATH):
                self.credentials = service_account.Credentials.from_service_account_file(
                    STORAGE_SERVICE_ACCOUNT_KEY_FILE_PATH,
                )
            else:
                self.credentials, _ = auth.default()
                
            self.client = storage.Client(project=settings.GCP.PROJECT_ID, credentials=self.credentials)
        except Exception as e:
            logger.exception(f"Failed to connect to GCP Storage for project {settings.GCP.PROJECT_ID}")
            raise e
            
    def get_client(self):
        return self.client
    
    def refresh_cred(self):
        if os.path.exists(STORAGE_SERVICE_ACCOUNT_KEY_FILE_PATH):
            return
        else:
            self.credentials.refresh(requests.Request())  
    
    def generate_signed_url_for_view(self, blob:Blob)->str:
        self.refresh_cred()
        return blob.generate_signed_url(
            expiration=dt.timedelta(hours=settings.Authentication.SignedURL.GET_EXPIRY_IN_HOURS), 
            method='GET',
            service_account_email=self.credentials.service_account_email,
            access_token=self.credentials.token)
    
    def generate_signed_url_for_upload(self, blob:Blob, content_type:str)->str:
        self.refresh_cred()
        return blob.generate_signed_url(
            expiration=dt.timedelta(minutes=settings.Authentication.SignedURL.PUT_EXPIRY_IN_MINUTES), 
            method='PUT', 
            content_type=content_type,
            service_account_email=self.credentials.service_account_email,
            access_token=self.credentials.token)
        
    @staticmethod
    def parse_gs_url(gs_url: str) -> dict:
        parts = gs_url.split("/")
        bucket_name = parts[2]
        file_name = "/".join(parts[3:])
        return {"bucket_name": bucket_name, "file_name": file_name, "gs_url": gs_url}

    @staticmethod
    def generate_signed_url_from_gs_url(gs_url: str, method='GET', content_type:str=None, send_file_name: bool=False) -> str | dict:
        parsed = StorageManager.parse_gs_url(gs_url)
        bucket = cloud_storage_client.bucket(parsed["bucket_name"])
        blob = bucket.blob(parsed["file_name"])
        if method == 'PUT':
            signed_url = StorageManager().generate_signed_url_for_upload(blob=blob, content_type=content_type)
        else:
            signed_url = StorageManager().generate_signed_url_for_view(blob=blob)  

        if send_file_name:
            return {"file_name": parsed["file_name"], "signed_url": signed_url, "gs_url": gs_url}
        return signed_url
    
    @staticmethod
    def total_files_in_paths(storage_locations:list[str])->int:
        total_file_count = 0
        for storage_location in storage_locations:
            parsed = StorageManager.parse_gs_url(storage_location)
            bucket = cloud_storage_client.bucket(parsed["bucket_name"])
            folder = parsed["file_name"]
            file_count = len(list(bucket.list_blobs(prefix=folder)))
            total_file_count += file_count
        
        return total_file_count
    
    @staticmethod
    def get_image_repos_for_project(user_id:str, project_id:str)->list[str]:
        _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
        
        project_doc = project_ref.get()
        if not project_doc.exists:
            logger.error(f"Unable to fetch project for user '{user_id}' and project '{project_id}'")
            return []
        
        property_id = project_doc.to_dict().get("property_id", None)
        
        image_repos = []
        if property_id: # Property repo needs to be 1st (Hero shot)
            property_cloud_path = CloudPath(
                bucket_id=settings.GCP.Storage.PROPERTIES_BUCKET,
                path=Path(f'{property_id}/Images') # Note the 'I' here vs 'i' in project images'. Bummer! 
            )
            image_repos.append(property_cloud_path.full_path())
            
        project_cloud_path = CloudPath(
            bucket_id=settings.GCP.Storage.USER_BUCKET,
            path=Path(f'{user_id}/{project_id}/images')
        )
        image_repos.append(project_cloud_path.full_path())
        
        return image_repos

    @staticmethod
    def get_video_repos_for_project(user_id: str, project_id: str) -> list[str]:
        """
        Get video storage paths following ADR-001 conventions
        Returns list of GCS paths containing videos and scene clips
        """
        try:
            video_repos = []
            
            # Raw videos path
            videos_cloud_path = CloudPath(
                bucket_id=settings.GCP.Storage.USER_BUCKET,
                path=Path(f'{user_id}/{project_id}/videos')
            )
            video_repos.append(videos_cloud_path.full_path())
            
            # Scene clips path  
            scene_clips_cloud_path = CloudPath(
                bucket_id=settings.GCP.Storage.USER_BUCKET,
                path=Path(f'{user_id}/{project_id}/scene_clips')
            )
            video_repos.append(scene_clips_cloud_path.full_path())
            
            return video_repos
            
        except Exception as e:
            logger.exception(f"Failed to get video repos for project {project_id}: {e}")
            return []

    @staticmethod
    def get_all_media_repos_for_project(user_id: str, project_id: str) -> dict[str, list[str]]:
        """
        Get all media repositories organized by type following ADR-001 conventions
        Returns dict with 'images' and 'videos' keys containing respective storage paths
        """
        try:
            return {
                'images': StorageManager.get_image_repos_for_project(user_id, project_id),
                'videos': StorageManager.get_video_repos_for_project(user_id, project_id)
            }
        except Exception as e:
            logger.exception(f"Failed to get media repos for project {project_id}: {e}")
            return {'images': [], 'videos': []}

    # NEW: Video and scene clip storage methods with lazy loading
    @staticmethod
    def get_scene_clips_for_project(user_id: str, project_id: str) -> list[str]:
        """
        Get scene clip storage paths following ADR-001 conventions
        Returns list of GCS paths containing scene clips
        """
        try:
            _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            
            project_doc = project_ref.get()
            if not project_doc.exists:
                logger.error(f"Unable to fetch project for user '{user_id}' and project '{project_id}'")
                return []
            
            # Scene clips are stored in dedicated scene_clips folder per ADR-001
            scene_clips_cloud_path = CloudPath(
                bucket_id=settings.GCP.Storage.USER_BUCKET,
                path=Path(f'{user_id}/{project_id}/scene_clips')
            )
            
            return [scene_clips_cloud_path.full_path()]
            
        except Exception as e:
            logger.exception(f"Failed to get scene clips for project {project_id}: {e}")
            return []

    @staticmethod
    def upload_video_to_gcs(video_file_path: str, user_id: str, project_id: str, 
                           video_filename: str) -> str:
        """
        Upload original video file to GCS with lazy approach
        Returns GCS URL of uploaded video
        """
        try:
            video_cloud_path = CloudPath(
                bucket_id=settings.GCP.Storage.USER_BUCKET,
                path=Path(f'{user_id}/{project_id}/videos/{video_filename}')
            )
            
            # Upload video file
            StorageManager.save_blob(
                source_file=Path(video_file_path),
                path=video_cloud_path
            )
            
            gs_url = video_cloud_path.full_path()
            logger.info(f"[STORAGE] Uploaded video to {gs_url}")
            return gs_url
            
        except Exception as e:
            logger.exception(f"Failed to upload video to GCS: {e}")
            raise

    @staticmethod
    def upload_scene_clip_to_gcs(clip_file_path: str, user_id: str, project_id: str, 
                                scene_id: str) -> str:
        """
        Upload extracted scene clip to GCS following ADR-001 conventions
        Returns GCS URL of uploaded scene clip
        """
        try:
            clip_filename = f"{scene_id}.mp4"
            scene_cloud_path = CloudPath(
                bucket_id=settings.GCP.Storage.USER_BUCKET,
                path=Path(f'{user_id}/{project_id}/scene_clips/{clip_filename}')
            )
            
            # Upload scene clip file
            StorageManager.save_blob(
                source_file=Path(clip_file_path),
                path=scene_cloud_path
            )
            
            gs_url = scene_cloud_path.full_path()
            logger.info(f"[STORAGE] Uploaded scene clip to {gs_url}")
            return gs_url
            
        except Exception as e:
            logger.exception(f"Failed to upload scene clip to GCS: {e}")
            raise

    @staticmethod
    def generate_scene_thumbnail(scene_clip_gs_url: str, timestamp: float = 1.0) -> str:
        """
        Generate thumbnail for scene clip (lazy approach - placeholder for now)
        In production, this would extract a frame from the video clip
        """
        try:
            # For now, return a placeholder thumbnail URL
            # In production, this would use FFmpeg to extract a frame
            parsed = StorageManager.parse_gs_url(scene_clip_gs_url)
            thumbnail_filename = parsed["file_name"].replace(".mp4", "_thumb.jpg")
            
            thumbnail_cloud_path = CloudPath(
                bucket_id=parsed["bucket_name"],
                path=Path(parsed["file_name"]).parent / "thumbnails" / thumbnail_filename
            )
            
            # Mock thumbnail generation - in production, extract actual frame
            thumbnail_gs_url = thumbnail_cloud_path.full_path()
            logger.debug(f"[STORAGE] Generated thumbnail placeholder: {thumbnail_gs_url}")
            
            return thumbnail_gs_url
            
        except Exception as e:
            logger.exception(f"Failed to generate scene thumbnail: {e}")
            return ""

    @staticmethod
    def get_video_metadata_from_gcs(video_gs_url: str) -> dict:
        """
        Extract video metadata from GCS file (lazy approach)
        In production, this would use FFprobe or similar
        """
        try:
            # Mock metadata extraction for development
            # In production, download video temporarily and extract real metadata
            metadata = {
                "duration": 120.0,  # Mock 2-minute video
                "fps": 30,
                "resolution": [1920, 1080],
                "aspect_ratio": 1.77,
                "orientation": "landscape",
                "has_audio": True,
                "file_size_mb": 85.2
            }
            
            logger.debug(f"[STORAGE] Extracted metadata for {video_gs_url}: {metadata}")
            return metadata
            
        except Exception as e:
            logger.exception(f"Failed to extract video metadata: {e}")
            return {}

    @staticmethod
    def cleanup_temp_video_files(temp_paths: list[str]):
        """
        Clean up temporary video files with lazy approach
        """
        try:
            for temp_path in temp_paths:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    logger.debug(f"[STORAGE] Cleaned up temp file: {temp_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup temp files: {e}")

    @staticmethod
    def get_mixed_media_for_project(user_id: str, project_id: str) -> dict:
        """
        Get both images and scene clips for a project (lazy unified approach)
        Returns dict with 'images' and 'scene_clips' paths
        """
        try:
            return {
                'images': StorageManager.get_image_repos_for_project(user_id, project_id),
                'scene_clips': StorageManager.get_scene_clips_for_project(user_id, project_id)
            }
        except Exception as e:
            logger.exception(f"Failed to get mixed media for project {project_id}: {e}")
            return {'images': [], 'scene_clips': []}
            
    @staticmethod
    def gen_signed_urls_for_bucket(storage_location: str, excluded_gs_urls: list = [], 
                                  file_types: list[str] = None):
        """
        Generate signed URLs for files in a bucket with optional file type filtering
        
        Args:
            storage_location: GCS path to search
            excluded_gs_urls: List of GCS URLs to exclude
            file_types: List of file extensions to include (e.g. ['.jpg', '.mp4'])
                       If None, includes common image and video types
        """
        try:
            parsed = StorageManager.parse_gs_url(storage_location)
            bucket = cloud_storage_client.bucket(parsed["bucket_name"])
            folder = parsed["file_name"]
            blobs = list(bucket.list_blobs(prefix=folder))
            signed_urls = []
            current_time = dt.datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
            expiry_delta = dt.timedelta(hours=settings.Authentication.SignedURL.GET_EXPIRY_IN_HOURS)
            signature_expiry = current_time + expiry_delta 
            
            # Default file types if not specified
            if file_types is None:
                file_types = ['.jpg', '.jpeg', '.png', '.webp', '.avif', '.mp4', '.mov', '.webm', '.m4v']
            
            excluded_file_names = []
            for excluded_gs_url in excluded_gs_urls:
                excluded_file_names.append(StorageManager.parse_gs_url(excluded_gs_url).get("file_name"))
                
            for blob in blobs:
                # Skip excluded files
                if any(e in blob.name for e in excluded_file_names):
                    continue
                    
                # Skip files that don't match specified file types
                if file_types and not any(blob.name.lower().endswith(ext) for ext in file_types):
                    continue
                    
                url = StorageManager().generate_signed_url_for_view(blob=blob)    
                signed_urls.append({
                    "file_name": blob.name,
                    "signed_url": url,
                    "gs_url": f"gs://{parsed['bucket_name']}/{blob.name}",
                })
            return signed_urls, signature_expiry
        except Exception as e:
            logger.exception(e)
            return [], None

    @staticmethod
    def save_blobs(source_dir:Path, cloud_path:CloudPath):
        try:
            bucket = cloud_storage_client.bucket(cloud_path.bucket_id)
            if not bucket:
                raise FileNotFoundError(f"GCP Storage Bucket '{cloud_path.bucket_id}' not found in project '{settings.GCP.PROJECT_ID}'")
            
            if not source_dir.is_dir():
                raise IsADirectoryError(f"{source_dir} is not a directory. Must provide directory for bulk action")
            
            # Get all files in `directory` as Path objects.
            all_paths = source_dir.glob("*")
            
            # Filter so the list only includes files, not directories themselves.
            file_paths = [path for path in all_paths if path.is_file()]
    
            # These paths are relative to the current working directory. Next, make them
            # relative to `directory`
            relative_paths = [path.relative_to(source_dir) for path in file_paths]

            # Finally, convert them all to strings.
            string_paths = [str(path) for path in relative_paths]

            # Start the upload.
            results = transfer_manager.upload_many_from_filenames(
                bucket=bucket, filenames=string_paths, source_directory=source_dir, blob_name_prefix=f"{cloud_path.path}/"
            )
                
            for name, result in zip(string_paths, results):
                # The results list is either `None` or an exception for each filename in
                # the input list, in order.
                if isinstance(result, Exception):
                    logger.error(f"Failed to upload {name} due to exception: {result}")
            
        except Exception as e:
            raise e
        
    @staticmethod
    def save_blob(source_file:Path, cloud_path:CloudPath):
        try:
            bucket = cloud_storage_client.bucket(cloud_path.bucket_id)
            if not bucket:
                raise FileNotFoundError(f"GCP Storage Bucket '{cloud_path.bucket_id}' not found in project '{settings.GCP.PROJECT_ID}'")
            
            if not source_file.is_file():
                raise FileNotFoundError(f"{source_file} is not a file")
            
            blob = bucket.blob(str(cloud_path.path))
            blob.upload_from_filename(filename=source_file)
            
        except Exception as e:
            raise e
        
    @staticmethod
    def load_blobs(cloud_path:CloudPath, dest_dir:Path, excluded_files:list[str]=None)->dict:
        def _mapping(cloud_path:CloudPath, dest_dir:Path)->tuple[dict, dict]:
            l2c_mapping = {}
            c2l_mapping = {}
            bucket = cloud_storage_client.bucket(cloud_path.bucket_id)
            prefix = f"{cloud_path.path}/"
            blobs = bucket.list_blobs(prefix=prefix, delimiter='/')
            for blob in blobs:
                gs_url = f'gs://{cloud_path.bucket_id}/{blob.name}'
                if excluded_files and gs_url in excluded_files:
                    continue
                # Construct the local file path
                local_file_path = os.path.join(str(dest_dir), Path(blob.name).name)
                # Add to the mapping
                l2c_mapping[local_file_path] = gs_url
                c2l_mapping[gs_url] = local_file_path
            return l2c_mapping, c2l_mapping
                
        try:
            bucket = cloud_storage_client.bucket(cloud_path.bucket_id)
            if not bucket:
                raise FileNotFoundError(f"GCP Storage Bucket '{cloud_path.bucket_id}' not found in project '{settings.GCP.PROJECT_ID}'")
            
            prefix = f"{cloud_path.path}/"
            blobs = [blob for blob in bucket.list_blobs(prefix=prefix, delimiter='/') if not blob.name.endswith('/')]
            if excluded_files:
                filtered_blobs = []
                for blob in blobs:
                    gs_url = f'gs://{cloud_path.bucket_id}/{blob.name}'
                    if not gs_url in excluded_files:
                        filtered_blobs.append(blob)
            else:
                filtered_blobs = blobs

            _ = transfer_manager.download_many_to_path(
                bucket=bucket, 
                blob_names=[Path(blob.name).name for blob in filtered_blobs], 
                destination_directory=dest_dir, 
                blob_name_prefix=prefix
            )
        
            return _mapping(cloud_path=cloud_path, dest_dir=dest_dir)
        
        except Exception as e:
            raise e
        
    @staticmethod
    def load_blob(cloud_path:CloudPath, dest_file:Path):
        try:
            bucket = cloud_storage_client.bucket(cloud_path.bucket_id)
            if not bucket:
                raise FileNotFoundError(f"GCP Storage Bucket '{cloud_path.bucket_id}' not found in project '{settings.GCP.PROJECT_ID}'")
                      
            blob = bucket.blob(str(cloud_path.path))
            blob.download_to_filename(dest_file)
            
        except Exception as e:
            raise e
        
    @staticmethod
    def bucket_metadata(bucket_name:str):
        bucket = cloud_storage_client.get_bucket(bucket_name)

        print(f"ID: {bucket.id}")
        print(f"Name: {bucket.name}")
        print(f"Storage Class: {bucket.storage_class}")
        print(f"Location: {bucket.location}")
        print(f"Location Type: {bucket.location_type}")
        print(f"Cors: {bucket.cors}")
        print(f"Default Event Based Hold: {bucket.default_event_based_hold}")
        print(f"Default KMS Key Name: {bucket.default_kms_key_name}")
        print(f"Metageneration: {bucket.metageneration}")
        print(
            f"Public Access Prevention: {bucket.iam_configuration.public_access_prevention}"
        )
        print(f"Retention Effective Time: {bucket.retention_policy_effective_time}")
        print(f"Retention Period: {bucket.retention_period}")
        print(f"Retention Policy Locked: {bucket.retention_policy_locked}")
        print(f"Object Retention Mode: {bucket.object_retention_mode}")
        print(f"Requester Pays: {bucket.requester_pays}")
        print(f"Self Link: {bucket.self_link}")
        print(f"Time Created: {bucket.time_created}")
        print(f"Versioning Enabled: {bucket.versioning_enabled}")
        print(f"Labels: {bucket.labels}")
        
    @staticmethod
    def set_cors_policy(bucket_name:str):
        bucket = cloud_storage_client.get_bucket(bucket_name)
        cors_policy = [
            {
                'origin': settings.Authentication.ALLOWED_ORIGINS, 
                'method': ['GET', 'PUT', 'POST', 'OPTIONS'], 
                'responseHeader': ['Content-Type', 'Content-Length', 'Authorization'], 
                'maxAgeSeconds': 3600
            }
        ]
        bucket.cors = cors_policy
        bucket.patch()
        print(f"Set CORS policies for bucket {bucket.name} : {bucket.cors}")
    
    @staticmethod
    def delete_folder(folder_path: str):
        """Delete all blobs in a folder path"""
        try:
            # Parse the folder path to get bucket and prefix
            if folder_path.startswith('gs://'):
                # Handle gs:// URLs
                parts = folder_path.replace('gs://', '').split('/', 1)
                if len(parts) != 2:
                    raise ValueError(f"Invalid gs:// URL format: {folder_path}")
                bucket_name = parts[0]
                prefix = parts[1]
            else:
                # Handle bucket/path format
                parts = folder_path.split('/', 1)
                if len(parts) != 2:
                    raise ValueError(f"Invalid folder path format: {folder_path}")
                bucket_name = parts[0]
                prefix = parts[1]
            
            # Ensure prefix ends with '/' for folder-like behavior
            if not prefix.endswith('/'):
                prefix += '/'
            
            bucket = cloud_storage_client.bucket(bucket_name)
            blobs = bucket.list_blobs(prefix=prefix)
            
            deleted_count = 0
            for blob in blobs:
                blob.delete()
                deleted_count += 1
            
            logger.info(f"Deleted {deleted_count} blobs from folder: {folder_path}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete folder {folder_path}: {str(e)}")
            raise e

    @staticmethod
    def list_blobs_in_path(cloud_path: CloudPath) -> list[str]:
        """
        List all blob paths in a given cloud path without downloading them
        
        Args:
            cloud_path: CloudPath object specifying the location
            
        Returns:
            List of GCS URLs (gs://bucket/path/file.ext)
        """
        try:
            bucket = cloud_storage_client.bucket(cloud_path.bucket_id)
            if not bucket.exists():
                logger.debug(f"[STORAGE] Bucket {cloud_path.bucket_id} does not exist")
                return []
            
            prefix = f"{cloud_path.path}/"
            blobs = bucket.list_blobs(prefix=prefix, delimiter='/')
            
            blob_paths = []
            for blob in blobs:
                if not blob.name.endswith('/'):  # Skip directories
                    gs_url = f'gs://{cloud_path.bucket_id}/{blob.name}'
                    blob_paths.append(gs_url)
            
            logger.debug(f"[STORAGE] Found {len(blob_paths)} blobs in {cloud_path.full_path()}")
            return blob_paths
            
        except Exception as e:
            logger.debug(f"[STORAGE] No blobs found in path {cloud_path.full_path()}: {e}")
            return []
    
    @staticmethod
    def download_blob_to_file(gs_url: str, local_file_path: str):
        """
        Download a blob from GCS to a local file
        
        Args:
            gs_url: GCS URL of the blob
            local_file_path: Local path where to save the file
        """
        try:
            parsed = StorageManager.parse_gs_url(gs_url)
            bucket = cloud_storage_client.bucket(parsed["bucket_name"])
            blob = bucket.blob(parsed["file_name"])
            
            blob.download_to_filename(local_file_path)
            logger.debug(f"[STORAGE] Downloaded {gs_url} to {local_file_path}")
            
        except Exception as e:
            logger.error(f"[STORAGE] Failed to download {gs_url} to {local_file_path}: {e}")
            raise

# Lazy-loaded GCP Storage client with feature flag support
_gcp_storage_manager_instance = None

def get_gcp_storage_manager():
    """Get GCP Storage Manager with lazy initialization and feature flag support"""
    global _gcp_storage_manager_instance
    
    logger.info("[GCP_STORAGE] get_gcp_storage_manager() called - checking feature flags...")
    
    # Check if GCP storage is enabled
    if not settings.FeatureFlags.ENABLE_GCP_STORAGE:
        logger.warning("[GCP_STORAGE] GCP storage disabled via feature flag")
        return None
    
    # Check if storage provider is GCP or if it's needed as fallback
    if hasattr(settings, 'Storage') and settings.Storage.PROVIDER != "GCP":
        if settings.FeatureFlags.ENABLE_DIGITAL_OCEAN_STORAGE:
            logger.warning(f"[GCP_STORAGE] Storage provider is '{settings.Storage.PROVIDER}' and Digital Ocean is enabled - GCP storage should only be fallback")
        else:
            logger.info(f"[GCP_STORAGE] Storage provider is '{settings.Storage.PROVIDER}' but Digital Ocean disabled - allowing GCP storage as fallback")
    
    # Lazy initialization only if needed
    if _gcp_storage_manager_instance is None:
        try:
            logger.info("[GCP_STORAGE] Initializing GCP StorageManager...")
            _gcp_storage_manager_instance = StorageManager()
            logger.info("[GCP_STORAGE] GCP StorageManager initialized successfully")
        except Exception as e:
            logger.exception(f"[GCP_STORAGE] Failed to initialize GCP StorageManager: {e}")
            return None
    else:
        logger.info("[GCP_STORAGE] Using existing GCP StorageManager instance")
    
    return _gcp_storage_manager_instance


class LazyGCPStorageClient:
    """Lazy GCP Storage client that respects feature flags"""
    
    def __getattr__(self, name):
        """Delegate attribute access to the real storage client"""
        logger.info(f"[GCP_STORAGE] LazyGCPStorageClient.__getattr__() called for attribute: {name}")
        
        manager = get_gcp_storage_manager()
        if manager is None:
            logger.error(f"[GCP_STORAGE] GCP Storage Manager not available for attribute '{name}'")
            raise RuntimeError("GCP Storage Manager is not available (failed to initialize or disabled)")
        
        client = manager.get_client()
        return getattr(client, name)
    
    def __call__(self, *args, **kwargs):
        """Make it callable if needed"""
        logger.info("[GCP_STORAGE] LazyGCPStorageClient.__call__() called")
        
        manager = get_gcp_storage_manager()
        if manager is None:
            logger.error("[GCP_STORAGE] GCP Storage Manager not available for call")
            raise RuntimeError("GCP Storage Manager is not available (failed to initialize or disabled)")
        
        client = manager.get_client()
        return client(*args, **kwargs)
    
    def bucket(self, bucket_name):
        """Most common method - get bucket"""
        logger.info(f"[GCP_STORAGE] LazyGCPStorageClient.bucket() called for: {bucket_name}")
        
        manager = get_gcp_storage_manager()
        if manager is None:
            logger.error(f"[GCP_STORAGE] GCP Storage Manager not available for bucket: {bucket_name}")
            raise RuntimeError("GCP Storage Manager is not available (failed to initialize or disabled)")
        
        client = manager.get_client()
        return client.bucket(bucket_name)
    
    def get_bucket(self, bucket_name):
        """Another common method - get bucket with existence check"""
        logger.info(f"[GCP_STORAGE] LazyGCPStorageClient.get_bucket() called for: {bucket_name}")
        
        manager = get_gcp_storage_manager()
        if manager is None:
            logger.error(f"[GCP_STORAGE] GCP Storage Manager not available for get_bucket: {bucket_name}")
            raise RuntimeError("GCP Storage Manager is not available (failed to initialize or disabled)")
        
        client = manager.get_client()
        return client.get_bucket(bucket_name)

# Backward compatibility: cloud_storage_client behaves like the original but respects feature flags
cloud_storage_client = LazyGCPStorageClient()

####

# For testing purposes only
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Cloud Storage Manager')

    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument('-u', '--upload', action='store_true', help='upload to cloud')
    action_group.add_argument('-d', '--download', action='store_true', help='download from cloud')
    

    parser.add_argument('-b', '--bucket_id', required=True, type=str, help='Bucket ID')
    parser.add_argument('-c', '--cloud_path', required=True, type=Path, help='Cloud path prefix')
    
    parser.add_argument('-l', '--local_path', required=True, type=Path, help='File/Dir to upload from / download to')
    
    args = parser.parse_args()
    
    excluded_gs_urls = ['gs://editora-v2-properties/ChIJ8XMK2vy6j4ARfTn_3aRjtgs/Images/image36.jpg', 
                        'gs://editora-v2-properties/ChIJ8XMK2vy6j4ARfTn_3aRjtgs/Images/image1.jpg',
                        'gs://editora-v2-properties/ChIJ8XMK2vy6j4ARfTn_3aRjtgs/Images/image2.jpg']
    
    try:
        cloud_path = CloudPath(
            bucket_id=args.bucket_id,
            path=Path(args.cloud_path)
        )
        if args.upload:
            if args.local_path.is_dir():
                StorageManager.save_blobs(source_dir=args.local_path, path=cloud_path)
            else:
                StorageManager.save_blob(source_file=args.local_path, path=cloud_path)
        elif args.download:
            if args.local_path.is_dir():
                l2c_mapping, c2l_mapping = StorageManager.load_blobs(cloud_path=cloud_path, dest_dir=args.local_path, excluded_files=excluded_gs_urls)
                
                from pprint import pformat
                logger.success(pformat(l2c_mapping))
                logger.success(pformat(c2l_mapping))
            else:
                StorageManager.load_blob(cloud_path=cloud_path, dest_file=args.local_path)
                
    except Exception as e:
        logger.exception(e)
        
        
def main2():
    user_id = 'user-test-91821539-9f1f-40d2-b93c-a0ce69126ae3'
    project_id = '139684e7-6e37-4244-aa10-880d89ff94b4'
    
    image_repos = StorageManager.get_image_repos_for_project(
        user_id=user_id,
        project_id=project_id
    )
    
    from rich import print
    print(image_repos)
    
    images = [img for repo in image_repos \
        for img in StorageManager.gen_signed_urls_for_bucket(storage_location=repo)][0]
    print(images)
    
def main3():
    bucket_name = 'editora-v2-users'
    StorageManager.bucket_metadata(bucket_name=bucket_name)
    StorageManager.set_cors_policy(bucket_name=bucket_name)
    StorageManager.bucket_metadata(bucket_name=bucket_name)

if __name__ == '__main__':
    main()
