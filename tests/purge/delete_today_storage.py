#!/usr/bin/env python3
"""
Script to delete Cloud Storage property folders that were created today.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config.config import settings
from logger import logger
from gcp.storage import StorageManager
from gcp.storage_model import CloudPath

def delete_today_storage_properties():
    """Delete all Cloud Storage property folders that were created today"""
    
    try:
        # Get today's date in the configured timezone
        today = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        
        logger.info(f"Deleting Cloud Storage properties created between {today_start} and {today_end}")
        
        # Use the existing StorageManager
        storage_manager = StorageManager()
        
        # List all blobs in the bucket
        bucket_name = settings.GCP.Storage.PROPERTIES_BUCKET
        logger.info(f"Listing blobs from bucket: {bucket_name}")
        
        # Get the bucket
        bucket = storage_manager.client.bucket(bucket_name)
        blobs = bucket.list_blobs()
        
        # Track property IDs and their creation times
        property_folders = {}
        
        for blob in blobs:
            # Extract property ID from path (first part of the path)
            path_parts = blob.name.split('/')
            if len(path_parts) >= 2:
                property_id = path_parts[0]
                
                # Get blob creation time
                if hasattr(blob, 'time_created'):
                    created_time = blob.time_created
                    
                    # Check if created today
                    if today_start <= created_time <= today_end:
                        if property_id not in property_folders:
                            property_folders[property_id] = {
                                'created_time': created_time,
                                'files': []
                            }
                        property_folders[property_id]['files'].append(blob.name)
        
        # Delete the property folders
        deleted_count = 0
        failed_count = 0
        
        if property_folders:
            logger.info(f"Found {len(property_folders)} property folders to delete:")
            logger.info("=" * 80)
            
            for property_id, info in property_folders.items():
                logger.info(f"Deleting property folder: {property_id}")
                logger.info(f"Created: {info['created_time']}")
                logger.info(f"Files: {len(info['files'])}")
                
                try:
                    # Delete all blobs in this property folder
                    for file_path in info['files']:
                        blob = bucket.blob(file_path)
                        blob.delete()
                        logger.debug(f"Deleted: {file_path}")
                    
                    deleted_count += 1
                    logger.success(f"Successfully deleted property folder: {property_id}")
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to delete property folder {property_id}: {str(e)}")
                
                logger.info("-" * 40)
            
            logger.info("=" * 80)
            logger.success(f"Storage deletion complete! Deleted: {deleted_count}, Failed: {failed_count}")
            
        else:
            logger.info("No property folders found that were created today.")
            
    except Exception as e:
        logger.error(f"Error deleting today's storage properties: {str(e)}")
        raise

if __name__ == '__main__':
    delete_today_storage_properties() 