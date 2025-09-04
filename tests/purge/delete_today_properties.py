#!/usr/bin/env python3
"""
Script to delete Firestore documents and Cloud Storage objects in the properties collection that were created today.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from google.cloud.firestore_v1 import FieldFilter
from google.cloud.storage import Client as StorageClient

from config.config import settings
from logger import logger
from gcp.db import db_client

def delete_today_properties_firestore():
    """Delete all property documents that were created today in Firestore"""
    
    try:
        # Get today's date in the configured timezone
        today = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        
        logger.info(f"Deleting Firestore properties created between {today_start} and {today_end}")
        
        # Reference to the properties collection
        properties_ref = db_client.collection(settings.GCP.Firestore.PROPERTIES_COLLECTION_NAME)
        
        # Query for documents created today
        query = properties_ref.where(
            filter=FieldFilter("extraction_time", ">=", today_start)
        ).where(
            filter=FieldFilter("extraction_time", "<=", today_end)
        )
        
        # Get all documents that match the criteria
        docs = query.stream()
        
        deleted_count = 0
        failed_count = 0
        property_ids = []
        
        for doc in docs:
            try:
                doc_data = doc.to_dict()
                extraction_time = doc_data.get('extraction_time')
                property_id = doc.id
                address = doc_data.get('address', 'Unknown')
                
                logger.info(f"Deleting Firestore property: {property_id} - {address} (created: {extraction_time})")
                
                # Delete the document
                doc.reference.delete()
                deleted_count += 1
                property_ids.append(property_id)
                
                logger.success(f"Successfully deleted Firestore property: {property_id}")
                
            except Exception as e:
                logger.error(f"Failed to delete Firestore property {doc.id}: {str(e)}")
                failed_count += 1
        
        logger.success(f"Firestore deletion complete! Deleted: {deleted_count}, Failed: {failed_count}")
        return deleted_count, failed_count, property_ids
        
    except Exception as e:
        logger.exception(f"Error in delete_today_properties_firestore: {str(e)}")
        raise

def delete_today_properties_storage():
    """Delete all property objects that were created today in Cloud Storage"""
    
    try:
        # Get today's date in the configured timezone
        today = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        
        logger.info(f"Deleting Cloud Storage properties created between {today_start} and {today_end}")
        
        # Initialize Cloud Storage client
        storage_client = StorageClient()
        bucket = storage_client.bucket(settings.GCP.Storage.PROPERTIES_BUCKET)
        
        # List all blobs in the bucket
        blobs = bucket.list_blobs()
        
        deleted_count = 0
        failed_count = 0
        
        for blob in blobs:
            try:
                # Check if blob was created today
                if blob.time_created and today_start <= blob.time_created.replace(tzinfo=ZoneInfo('UTC')) <= today_end:
                    logger.info(f"Deleting Cloud Storage blob: {blob.name} (created: {blob.time_created})")
                    
                    # Delete the blob
                    blob.delete()
                    deleted_count += 1
                    
                    logger.success(f"Successfully deleted Cloud Storage blob: {blob.name}")
                    
            except Exception as e:
                logger.error(f"Failed to delete Cloud Storage blob {blob.name}: {str(e)}")
                failed_count += 1
        
        logger.success(f"Cloud Storage deletion complete! Deleted: {deleted_count}, Failed: {failed_count}")
        return deleted_count, failed_count
        
    except Exception as e:
        logger.exception(f"Error in delete_today_properties_storage: {str(e)}")
        raise

def delete_today_properties_combined():
    """Delete both Firestore documents and Cloud Storage objects created today"""
    
    logger.info("Starting combined deletion of today's properties...")
    
    # First delete Firestore documents
    firestore_deleted, firestore_failed, property_ids = delete_today_properties_firestore()
    
    # Then delete Cloud Storage objects
    storage_deleted, storage_failed = delete_today_properties_storage()
    
    total_deleted = firestore_deleted + storage_deleted
    total_failed = firestore_failed + storage_failed
    
    logger.success(f"Combined deletion complete!")
    logger.info(f"Firestore - Deleted: {firestore_deleted}, Failed: {firestore_failed}")
    logger.info(f"Cloud Storage - Deleted: {storage_deleted}, Failed: {storage_failed}")
    logger.info(f"Total - Deleted: {total_deleted}, Failed: {total_failed}")
    
    return {
        'firestore_deleted': firestore_deleted,
        'firestore_failed': firestore_failed,
        'storage_deleted': storage_deleted,
        'storage_failed': storage_failed,
        'total_deleted': total_deleted,
        'total_failed': total_failed,
        'property_ids': property_ids
    }

def list_today_properties():
    """List all property documents that were created today (without deleting)"""
    
    try:
        # Get today's date in the configured timezone
        today = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        
        logger.info(f"Listing properties created between {today_start} and {today_end}")
        
        # Reference to the properties collection
        properties_ref = db_client.collection(settings.GCP.Firestore.PROPERTIES_COLLECTION_NAME)
        
        # Query for documents created today
        query = properties_ref.where(
            filter=FieldFilter("extraction_time", ">=", today_start)
        ).where(
            filter=FieldFilter("extraction_time", "<=", today_end)
        )
        
        # Get all documents that match the criteria
        docs = query.stream()
        
        properties = []
        for doc in docs:
            doc_data = doc.to_dict()
            properties.append({
                'id': doc.id,
                'address': doc_data.get('address', 'Unknown'),
                'extraction_engine': doc_data.get('extraction_engine', 'Unknown'),
                'extraction_time': doc_data.get('extraction_time'),
                'has_script': bool(doc_data.get('script')),
                'script_preview': doc_data.get('script', '')[:100] + '...' if doc_data.get('script') else 'No script'
            })
        
        logger.info(f"Found {len(properties)} properties created today:")
        for prop in properties:
            logger.info(f"  - {prop['id']}: {prop['address']} ({prop['extraction_engine']}) - Script: {'Yes' if prop['has_script'] else 'No'}")
            if prop['has_script']:
                logger.info(f"    Script preview: {prop['script_preview']}")
        
        return properties
        
    except Exception as e:
        logger.exception(f"Error in list_today_properties: {str(e)}")
        raise

def list_today_storage():
    """List all Cloud Storage objects that were created today (without deleting)"""
    
    try:
        # Get today's date in the configured timezone
        today = datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)).date()
        today_start = datetime.combine(today, datetime.min.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        today_end = datetime.combine(today, datetime.max.time(), tzinfo=ZoneInfo(settings.General.TIMEZONE))
        
        logger.info(f"Listing Cloud Storage objects created between {today_start} and {today_end}")
        
        # Initialize Cloud Storage client
        storage_client = StorageClient()
        bucket = storage_client.bucket(settings.GCP.Storage.PROPERTIES_BUCKET)
        
        # List all blobs in the bucket
        blobs = bucket.list_blobs()
        
        today_blobs = []
        for blob in blobs:
            if blob.time_created and today_start <= blob.time_created.replace(tzinfo=ZoneInfo('UTC')) <= today_end:
                today_blobs.append({
                    'name': blob.name,
                    'size': blob.size,
                    'created': blob.time_created,
                    'updated': blob.updated
                })
        
        logger.info(f"Found {len(today_blobs)} Cloud Storage objects created today:")
        for blob in today_blobs:
            logger.info(f"  - {blob['name']} ({blob['size']} bytes, created: {blob['created']})")
        
        return today_blobs
        
    except Exception as e:
        logger.exception(f"Error in list_today_storage: {str(e)}")
        raise

def main():
    """Main function to handle command line arguments"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Delete or list properties created today')
    parser.add_argument('--action', choices=['list', 'delete-firestore', 'delete-storage', 'delete-all'], default='list', 
                       help='Action to perform: list (default), delete-firestore, delete-storage, or delete-all')
    parser.add_argument('--confirm', action='store_true', 
                       help='Confirm deletion (required for delete actions)')
    
    args = parser.parse_args()
    
    if args.action == 'list':
        logger.info("Listing properties created today...")
        properties = list_today_properties()
        print(f"\nFound {len(properties)} Firestore properties created today")
        
        logger.info("Listing Cloud Storage objects created today...")
        storage_objects = list_today_storage()
        print(f"Found {len(storage_objects)} Cloud Storage objects created today")
        
    elif args.action == 'delete-firestore':
        if not args.confirm:
            logger.error("Please use --confirm flag to confirm deletion")
            print("⚠️  WARNING: This will permanently delete all Firestore properties created today!")
            print("   Use --confirm flag to proceed with deletion")
            return
        
        logger.info("Deleting Firestore properties created today...")
        deleted, failed, property_ids = delete_today_properties_firestore()
        print(f"\nFirestore deletion complete!")
        print(f"✅ Deleted: {deleted}")
        print(f"❌ Failed: {failed}")
        
    elif args.action == 'delete-storage':
        if not args.confirm:
            logger.error("Please use --confirm flag to confirm deletion")
            print("⚠️  WARNING: This will permanently delete all Cloud Storage objects created today!")
            print("   Use --confirm flag to proceed with deletion")
            return
        
        logger.info("Deleting Cloud Storage objects created today...")
        deleted, failed = delete_today_properties_storage()
        print(f"\nCloud Storage deletion complete!")
        print(f"✅ Deleted: {deleted}")
        print(f"❌ Failed: {failed}")
        
    elif args.action == 'delete-all':
        if not args.confirm:
            logger.error("Please use --confirm flag to confirm deletion")
            print("⚠️  WARNING: This will permanently delete ALL properties and storage objects created today!")
            print("   Use --confirm flag to proceed with deletion")
            return
        
        logger.info("Deleting all properties and storage objects created today...")
        result = delete_today_properties_combined()
        print(f"\nCombined deletion complete!")
        print(f"🔥 Firestore - Deleted: {result['firestore_deleted']}, Failed: {result['firestore_failed']}")
        print(f"☁️  Cloud Storage - Deleted: {result['storage_deleted']}, Failed: {result['storage_failed']}")
        print(f"📊 Total - Deleted: {result['total_deleted']}, Failed: {result['total_failed']}")

if __name__ == "__main__":
    main() 