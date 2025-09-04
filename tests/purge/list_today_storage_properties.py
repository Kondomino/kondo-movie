#!/usr/bin/env python3
"""
Script to list Cloud Storage property IDs that were created today for manual deletion.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from config.config import settings
from logger import logger
from gcp.storage import StorageManager
from gcp.storage_model import CloudPath

def list_today_storage_properties():
    """List all Cloud Storage property folders that were created today"""
    
    try:
        # Get today's date in the configured timezone
        today = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        
        logger.info(f"Listing Cloud Storage properties created between {today_start} and {today_end}")
        
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
        
        # Display results
        if property_folders:
            logger.info(f"Found {len(property_folders)} property folders created today:")
            logger.info("=" * 80)
            
            for property_id, info in property_folders.items():
                logger.info(f"Property ID: {property_id}")
                logger.info(f"Created: {info['created_time']}")
                logger.info(f"Files: {len(info['files'])}")
                logger.info("-" * 40)
                
                # Show first few files as examples
                for i, file_path in enumerate(info['files'][:3]):
                    logger.info(f"  {file_path}")
                if len(info['files']) > 3:
                    logger.info(f"  ... and {len(info['files']) - 3} more files")
                logger.info("")
            
            logger.info("=" * 80)
            logger.info("To delete these manually, use the following gsutil commands:")
            logger.info("")
            
            for property_id in property_folders.keys():
                logger.info(f"gsutil -m rm -r gs://{settings.GCP.Storage.PROPERTIES_BUCKET}/{property_id}/")
            
        else:
            logger.info("No property folders found that were created today.")
            
    except Exception as e:
        logger.error(f"Error listing today's storage properties: {str(e)}")
        raise

if __name__ == '__main__':
    list_today_storage_properties() 