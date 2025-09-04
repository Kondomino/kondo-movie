from pathlib import Path
import argparse
import os
import datetime as dt
from zoneinfo import ZoneInfo
from typing import Any, List, Dict, Optional
import tempfile
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError, NoCredentialsError

from logger import logger
from config.config import settings
from digitalocean.storage_model import CloudPath
from utils.session_utils import get_session_refs_by_ids

class DigitalOceanStorageManager:
    """
    Digital Ocean Spaces storage manager using S3-compatible API
    Maintains compatibility with existing GCP StorageManager interface
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.setup()
        return cls._instance

    def setup(self):
        """Initialize Digital Ocean Spaces client"""
        try:
            # Get Digital Ocean Spaces credentials from environment
            access_key = os.getenv('DIGITAL_OCEAN_STORAGE_KEY_ID')
            secret_key = os.getenv('DIGITAL_OCEAN_STORAGE_SECRET')
            endpoint_url = os.getenv('DIGITAL_OCEAN_ORIGIN_ENDPOINT')
            
            if not all([access_key, secret_key, endpoint_url]):
                raise ValueError("Missing Digital Ocean Spaces credentials. Required: DIGITAL_OCEAN_STORAGE_KEY_ID, DIGITAL_OCEAN_STORAGE_SECRET, DIGITAL_OCEAN_ORIGIN_ENDPOINT")
            
            # Initialize boto3 client for Digital Ocean Spaces
            self.client = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name='nyc3',  # Digital Ocean Spaces region
                config=Config(
                    signature_version='s3v4',
                    s3={'addressing_style': 'virtual'}
                )
            )
            
            # Store endpoints for URL generation
            self.origin_endpoint = endpoint_url
            self.cdn_endpoint = os.getenv('DIGITAL_OCEAN_CDN_ENDPOINT')
            
            logger.info(f"[DO_STORAGE] Successfully connected to Digital Ocean Spaces")
            logger.info(f"[DO_STORAGE] Origin endpoint: {self.origin_endpoint}")
            logger.info(f"[DO_STORAGE] CDN endpoint: {self.cdn_endpoint or 'Not configured'}")
            
        except Exception as e:
            logger.exception(f"Failed to connect to Digital Ocean Spaces: {e}")
            raise e

    def get_client(self):
        """Get the boto3 S3 client"""
        return self.client

    def generate_signed_url_for_view(self, bucket: str, key: str) -> str:
        """
        Generate signed URL for viewing/downloading a file
        Compatible with GCP StorageManager interface
        """
        try:
            expiration = settings.Authentication.SignedURL.GET_EXPIRY_IN_HOURS * 3600  # Convert hours to seconds
            
            signed_url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket, 'Key': key},
                ExpiresIn=expiration
            )
            
            logger.debug(f"[DO_STORAGE] Generated signed URL for {bucket}/{key}")
            return signed_url
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to generate signed URL for {bucket}/{key}: {e}")
            raise e

    def generate_signed_url_for_upload(self, bucket: str, key: str, content_type: str) -> str:
        """
        Generate signed URL for uploading a file
        Compatible with GCP StorageManager interface
        """
        try:
            expiration = settings.Authentication.SignedURL.PUT_EXPIRY_IN_MINUTES * 60  # Convert minutes to seconds
            
            signed_url = self.client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': bucket, 
                    'Key': key,
                    'ContentType': content_type
                },
                ExpiresIn=expiration
            )
            
            logger.debug(f"[DO_STORAGE] Generated upload URL for {bucket}/{key}")
            return signed_url
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to generate upload URL for {bucket}/{key}: {e}")
            raise e

    @staticmethod
    def parse_s3_url(s3_url: str) -> dict:
        """
        Parse S3 URL to extract bucket and key
        Compatible with GCP StorageManager.parse_gs_url interface
        """
        if s3_url.startswith('s3://'):
            parts = s3_url.replace('s3://', '').split('/', 1)
            if len(parts) == 2:
                return {
                    "bucket_name": parts[0],
                    "file_name": parts[1],
                    "s3_url": s3_url
                }
        
        raise ValueError(f"Invalid S3 URL format: {s3_url}")

    @staticmethod
    def generate_signed_url_from_s3_url(s3_url: str, method='GET', content_type: str = None, send_file_name: bool = False) -> str | dict:
        """
        Generate signed URL from S3 URL
        Compatible with GCP StorageManager.generate_signed_url_from_gs_url interface
        """
        try:
            parsed = DigitalOceanStorageManager.parse_s3_url(s3_url)
            storage_manager = DigitalOceanStorageManager()
            
            if method == 'PUT':
                if not content_type:
                    content_type = 'application/octet-stream'
                signed_url = storage_manager.generate_signed_url_for_upload(
                    bucket=parsed["bucket_name"],
                    key=parsed["file_name"],
                    content_type=content_type
                )
            else:
                signed_url = storage_manager.generate_signed_url_for_view(
                    bucket=parsed["bucket_name"],
                    key=parsed["file_name"]
                )

            if send_file_name:
                return {
                    "file_name": parsed["file_name"],
                    "signed_url": signed_url,
                    "s3_url": s3_url
                }
            return signed_url
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to generate signed URL from S3 URL {s3_url}: {e}")
            raise e

    def upload_file(self, source_file: Path, bucket: str, key: str, content_type: str = None) -> str:
        """
        Upload a file to Digital Ocean Spaces
        Returns S3 URL of uploaded file
        """
        try:
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
                
            self.client.upload_file(
                str(source_file),
                bucket,
                key,
                ExtraArgs=extra_args
            )
            
            s3_url = f"s3://{bucket}/{key}"
            logger.info(f"[DO_STORAGE] Uploaded file to {s3_url}")
            return s3_url
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to upload file {source_file} to {bucket}/{key}: {e}")
            raise e

    def download_file(self, bucket: str, key: str, dest_file: Path):
        """
        Download a file from Digital Ocean Spaces
        """
        try:
            # Ensure destination directory exists
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            self.client.download_file(bucket, key, str(dest_file))
            logger.debug(f"[DO_STORAGE] Downloaded {bucket}/{key} to {dest_file}")
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to download {bucket}/{key} to {dest_file}: {e}")
            raise e

    def list_objects(self, bucket: str, prefix: str = "") -> List[dict]:
        """
        List objects in a bucket with optional prefix
        """
        try:
            objects = []
            paginator = self.client.get_paginator('list_objects_v2')
            
            page_iterator = paginator.paginate(
                Bucket=bucket,
                Prefix=prefix
            )
            
            for page in page_iterator:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects.append({
                            'Key': obj['Key'],
                            'Size': obj['Size'],
                            'LastModified': obj['LastModified'],
                            'ETag': obj['ETag']
                        })
            
            logger.debug(f"[DO_STORAGE] Found {len(objects)} objects in {bucket} with prefix '{prefix}'")
            return objects
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to list objects in {bucket} with prefix '{prefix}': {e}")
            return []

    def delete_object(self, bucket: str, key: str):
        """
        Delete an object from Digital Ocean Spaces
        """
        try:
            self.client.delete_object(Bucket=bucket, Key=key)
            logger.info(f"[DO_STORAGE] Deleted object {bucket}/{key}")
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to delete object {bucket}/{key}: {e}")
            raise e

    def delete_objects(self, bucket: str, keys: List[str]):
        """
        Delete multiple objects from Digital Ocean Spaces
        """
        try:
            if not keys:
                return
                
            # Batch delete (max 1000 objects per request)
            batch_size = 1000
            for i in range(0, len(keys), batch_size):
                batch_keys = keys[i:i + batch_size]
                delete_objects = [{'Key': key} for key in batch_keys]
                
                self.client.delete_objects(
                    Bucket=bucket,
                    Delete={'Objects': delete_objects}
                )
                
            logger.info(f"[DO_STORAGE] Deleted {len(keys)} objects from {bucket}")
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to delete objects from {bucket}: {e}")
            raise e

    def object_exists(self, bucket: str, key: str) -> bool:
        """
        Check if an object exists in Digital Ocean Spaces
        """
        try:
            self.client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                logger.error(f"[DO_STORAGE] Error checking if object exists {bucket}/{key}: {e}")
                raise e

    # Compatibility methods with GCP StorageManager interface
    
    @staticmethod
    def save_blob(source_file: Path, cloud_path: CloudPath):
        """
        Save a single file to Digital Ocean Spaces
        Compatible with GCP StorageManager.save_blob interface
        """
        try:
            storage_manager = DigitalOceanStorageManager()
            
            if not source_file.is_file():
                raise FileNotFoundError(f"{source_file} is not a file")
            
            # Upload file
            s3_url = storage_manager.upload_file(
                source_file=source_file,
                bucket=cloud_path.bucket_id,
                key=str(cloud_path.path)
            )
            
            logger.info(f"[DO_STORAGE] Saved blob: {s3_url}")
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to save blob {source_file} to {cloud_path.full_path()}: {e}")
            raise e

    @staticmethod
    def save_blobs(source_dir: Path, cloud_path: CloudPath):
        """
        Save multiple files from directory to Digital Ocean Spaces
        Compatible with GCP StorageManager.save_blobs interface
        """
        try:
            storage_manager = DigitalOceanStorageManager()
            
            if not source_dir.is_dir():
                raise IsADirectoryError(f"{source_dir} is not a directory")
            
            # Get all files in directory
            file_paths = [path for path in source_dir.glob("*") if path.is_file()]
            
            uploaded_count = 0
            for file_path in file_paths:
                relative_path = file_path.relative_to(source_dir)
                key = f"{cloud_path.path}/{relative_path}"
                
                try:
                    storage_manager.upload_file(
                        source_file=file_path,
                        bucket=cloud_path.bucket_id,
                        key=key
                    )
                    uploaded_count += 1
                except Exception as e:
                    logger.error(f"[DO_STORAGE] Failed to upload {file_path}: {e}")
            
            logger.info(f"[DO_STORAGE] Uploaded {uploaded_count}/{len(file_paths)} files to {cloud_path.full_path()}")
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to save blobs from {source_dir} to {cloud_path.full_path()}: {e}")
            raise e

    @staticmethod
    def load_blob(cloud_path: CloudPath, dest_file: Path):
        """
        Download a single file from Digital Ocean Spaces
        Compatible with GCP StorageManager.load_blob interface
        """
        try:
            storage_manager = DigitalOceanStorageManager()
            
            storage_manager.download_file(
                bucket=cloud_path.bucket_id,
                key=str(cloud_path.path),
                dest_file=dest_file
            )
            
            logger.info(f"[DO_STORAGE] Loaded blob from {cloud_path.full_path()} to {dest_file}")
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to load blob from {cloud_path.full_path()} to {dest_file}: {e}")
            raise e

    @staticmethod
    def download_blob_to_file(s3_url: str, local_file_path: str):
        """
        Download a blob from S3 URL to local file
        Compatible with GCP StorageManager.download_blob_to_file interface
        """
        try:
            parsed = DigitalOceanStorageManager.parse_s3_url(s3_url)
            storage_manager = DigitalOceanStorageManager()
            
            storage_manager.download_file(
                bucket=parsed["bucket_name"],
                key=parsed["file_name"],
                dest_file=Path(local_file_path)
            )
            
            logger.debug(f"[DO_STORAGE] Downloaded {s3_url} to {local_file_path}")
            
        except Exception as e:
            logger.error(f"[DO_STORAGE] Failed to download {s3_url} to {local_file_path}: {e}")
            raise e

# Create a Digital Ocean Spaces client instance
ocean_storage_client = DigitalOceanStorageManager().get_client()

def main():
    """Test Digital Ocean Spaces functionality"""
    parser = argparse.ArgumentParser(description='Digital Ocean Spaces Manager')

    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument('-u', '--upload', action='store_true', help='upload to spaces')
    action_group.add_argument('-d', '--download', action='store_true', help='download from spaces')
    action_group.add_argument('-l', '--list', action='store_true', help='list objects in spaces')

    parser.add_argument('-b', '--bucket', required=True, type=str, help='Bucket name')
    parser.add_argument('-k', '--key', type=str, help='Object key/path')
    parser.add_argument('-f', '--file', type=Path, help='Local file path')

    args = parser.parse_args()

    try:
        storage_manager = DigitalOceanStorageManager()
        
        if args.upload:
            if not args.key or not args.file:
                raise ValueError("Upload requires --key and --file arguments")
            
            s3_url = storage_manager.upload_file(
                source_file=args.file,
                bucket=args.bucket,
                key=args.key
            )
            print(f"Uploaded to: {s3_url}")
            
        elif args.download:
            if not args.key or not args.file:
                raise ValueError("Download requires --key and --file arguments")
            
            storage_manager.download_file(
                bucket=args.bucket,
                key=args.key,
                dest_file=args.file
            )
            print(f"Downloaded to: {args.file}")
            
        elif args.list:
            objects = storage_manager.list_objects(
                bucket=args.bucket,
                prefix=args.key or ""
            )
            print(f"Found {len(objects)} objects:")
            for obj in objects[:10]:  # Show first 10 objects
                print(f"  {obj['Key']} ({obj['Size']} bytes)")
            
    except Exception as e:
        logger.exception(f"Digital Ocean Spaces operation failed: {e}")

if __name__ == '__main__':
    main()
