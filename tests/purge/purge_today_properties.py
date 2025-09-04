#!/usr/bin/env python3
"""
Combined script to purge Firestore documents and Cloud Storage objects created today.
"""

import sys
import os
import argparse
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from google.cloud.firestore_v1 import FieldFilter

from config.config import settings
from logger import logger
from gcp.db import db_client
from gcp.storage import StorageManager

def delete_today_properties_firestore():
    """Delete all property documents that were created today in Firestore"""
    
    try:
        # Get today's date in the configured timezone
        today = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        
        logger.info(f"Deleting Firestore properties created between {today_start} and {today_end}")
        
        # Query Firestore for properties created today
        collection_ref = db_client.collection(settings.GCP.Firestore.PROPERTIES_COLLECTION_NAME)
        query = collection_ref.where(filter=FieldFilter("extraction_time", ">=", today_start)).where(filter=FieldFilter("extraction_time", "<=", today_end))
        
        docs = query.stream()
        deleted_count = 0
        failed_count = 0
        
        for doc in docs:
            try:
                logger.info(f"Deleting Firestore property: {doc.id} - {doc.get('address', 'Unknown')} (created: {doc.get('extraction_time')})")
                doc.reference.delete()
                deleted_count += 1
                logger.success(f"Successfully deleted Firestore property: {doc.id}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to delete Firestore property {doc.id}: {str(e)}")
        
        logger.success(f"Firestore deletion complete! Deleted: {deleted_count}, Failed: {failed_count}")
        return deleted_count, failed_count
        
    except Exception as e:
        logger.error(f"Error in delete_today_properties_firestore: {str(e)}")
        raise

def delete_today_properties_storage():
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
            
        return deleted_count, failed_count
        
    except Exception as e:
        logger.error(f"Error in delete_today_properties_storage: {str(e)}")
        raise

def purge_today_properties_combined():
    """Delete both Firestore documents and Cloud Storage objects created today"""
    
    logger.info("Starting combined deletion of today's properties...")
    
    # Delete Firestore documents
    firestore_deleted, firestore_failed = delete_today_properties_firestore()
    
    # Delete Cloud Storage objects
    storage_deleted, storage_failed = delete_today_properties_storage()
    
    # Summary
    total_deleted = firestore_deleted + storage_deleted
    total_failed = firestore_failed + storage_failed
    
    logger.info("=" * 80)
    logger.info("COMBINED PURGE SUMMARY:")
    logger.info(f"Firestore - Deleted: {firestore_deleted}, Failed: {firestore_failed}")
    logger.info(f"Cloud Storage - Deleted: {storage_deleted}, Failed: {storage_failed}")
    logger.info(f"TOTAL - Deleted: {total_deleted}, Failed: {total_failed}")
    logger.info("=" * 80)
    
    return total_deleted, total_failed

def main():
    parser = argparse.ArgumentParser(description='Purge today\'s properties from Firestore and Cloud Storage')
    parser.add_argument('--action', choices=['list', 'delete-firestore', 'delete-storage', 'delete-all'], 
                       default='list', help='Action to perform')
    parser.add_argument('--confirm', action='store_true', help='Confirm deletion (required for delete actions)')
    
    args = parser.parse_args()
    
    if args.action in ['delete-firestore', 'delete-storage', 'delete-all'] and not args.confirm:
        logger.error("Please use --confirm flag to proceed with deletion")
        return
    
    try:
        if args.action == 'list':
            logger.info("Listing today's properties (no deletion)...")
            # Import and run the list function
            from list_today_storage_properties import list_today_storage_properties
            list_today_storage_properties()
            
        elif args.action == 'delete-firestore':
            logger.info("Deleting Firestore properties created today...")
            delete_today_properties_firestore()
            
        elif args.action == 'delete-storage':
            logger.info("Deleting Cloud Storage properties created today...")
            delete_today_properties_storage()
            
        elif args.action == 'delete-all':
            logger.info("Deleting all properties and storage objects created today...")
            purge_today_properties_combined()
            
    except Exception as e:
        logger.error(f"Error in main: {str(e)}")
        raise

if __name__ == '__main__':
    main() 