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

# NOTE: `from utils.session_utils import get_session_refs_by_ids` is imported
# lazily inside the methods that need it, to avoid forcing a DB connection at
# module-load time for callers that only want to use the GCS surface (signed
# URLs, raw upload/download). Same pattern as `movie_maker/edl_manager.py`.

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
    
    # ------------------------------------------------------------------
    # Project-aware helpers below were Editora-era (Firestore-backed
    # session refs to derive bucket prefixes per user/project). Removed
    # in PR k4 alongside the Firestore purge — kondos-api now owns all
    # project state and tells the engine what URLs to fetch directly via
    # the v2 contract. Only raw gs:// I/O remains.
    # ------------------------------------------------------------------

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
