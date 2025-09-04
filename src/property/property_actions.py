import uuid
import httpx
import json
from zoneinfo import ZoneInfo
from fastapi import HTTPException

from logger import logger
from config.config import settings
from property.property_actions_model import *
from property.property_manager import PropertyManager
from property.address import Address
from video.video_actions import VideoActionsHandler
from gcp.storage import StorageManager
from gcp.db import DBManager
from project.project_manager import ProjectManager

class PropertyActionsHandler:
    def __init__(self):
        logger.info("PropertyActionsHandler initialized")

    def _purge_firestore_cache(self, property_id: str) -> bool:
        """Purge property cache from Firestore by deleting the property document."""
        try:
            firestore_mgr = DBManager()
            document_path = f"properties/{property_id}"
            deleted_count = firestore_mgr.delete_document(document_path)
            success = deleted_count > 0
            
            if success:
                logger.info(f"Successfully purged Firestore cache for property_id: {property_id} (deleted {deleted_count} document)")
            else:
                logger.warning(f"No Firestore document found to purge for property_id: {property_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Failed to purge Firestore cache for property_id: {property_id}: {str(e)}")
            return False

    def _purge_cloud_storage_cache(self, property_id: str) -> bool:
        """Purge property cache from Cloud Storage by deleting all files in the property folder."""
        try:
            storage_mgr = StorageManager()
            # Use the full gs:// URL format for better compatibility
            storage_path = f"gs://editora-v2-properties/{property_id}"
            deleted_count = storage_mgr.delete_folder(storage_path)
            success = deleted_count > 0
            
            if success:
                logger.info(f"Successfully purged Cloud Storage cache for property_id: {property_id} (deleted {deleted_count} files)")
            else:
                logger.warning(f"No Cloud Storage files found to purge for property_id: {property_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"Failed to purge Cloud Storage cache for property_id: {property_id}: {str(e)}")
            return False

    def _orchestrate_purge_operations(self, property_id: str) -> tuple[bool, bool]:
        """Orchestrate all purge operations for a property."""
        logger.info(f"Starting purge orchestration for property_id: {property_id}")
        
        # Execute purge operations
        firestore_deleted = self._purge_firestore_cache(property_id)
        storage_deleted = self._purge_cloud_storage_cache(property_id)
        
        return firestore_deleted, storage_deleted

    def purge_property_cache(self, user_id: str, request: PurgePropertyCacheRequest) -> PurgePropertyCacheResponse:
        """Purge cache for a specific property from both Firestore and Cloud Storage"""
        logger.info(f"Starting purge_property_cache for user_id: {user_id}, property_id: {request.property_id}")
        
        try:
            property_id = request.property_id
            
            # Orchestrate all purge operations
            firestore_deleted, storage_deleted = self._orchestrate_purge_operations(property_id)
            
            # Generate response message
            if firestore_deleted or storage_deleted:
                message = f"Cache purge completed for property {property_id}"
                logger.success(f"Cache purge completed for property_id: {property_id} - Firestore: {firestore_deleted}, Storage: {storage_deleted}")
            else:
                message = f"No cache was purged for property {property_id}"
                logger.warning(f"No cache was purged for property_id: {property_id}")
            
            return PurgePropertyCacheResponse(
                message=message,
                property_id=property_id,
                firestore_deleted=firestore_deleted,
                storage_deleted=storage_deleted
            )
            
        except Exception as e:
            logger.exception(f"Error in purge_property_cache for user_id: {user_id}, property_id: {request.property_id}: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))

    def fetch_property_details(self, user_id:str, request: FetchPropertyDetailsRequest) -> FetchPropertyDetailsResponse:
        logger.info(f"Starting fetch_property_details for user_id: {user_id}, property_address: '{request.property_address}'")
        if request.title:
            logger.info(f"Title provided: '{request.title}'")
        try:
            logger.info(f"Creating FetchPropertyRequest for property_id: {request.property_id}")
            fetch_property_request = FetchPropertyRequest(
                request_id=request.property_id,
                property_address=request.property_address,
                address_input_type=request.address_input_type,
                title=request.title,
            )
            
            logger.info(f"Calling fetch_property with request_id: {fetch_property_request.request_id}")
            fetch_property_response = self.fetch_property(request=fetch_property_request, user_id=user_id)
            
            logger.info(f"fetch_property completed with state: {fetch_property_response.result.state}")
            if fetch_property_response.result.state != ActionStatus.State.SUCCESS:
                logger.error(f"Property fetch failed with state: {fetch_property_response.result.state}, reason: {fetch_property_response.result.reason}")
                raise HTTPException(status_code=500, detail=f"Failed to extract details for property: {request.property_address}")
            
            logger.info(f"Property fetch successful, processing property details")
            property_data = fetch_property_response.property_details.model_dump()
            
            # Get source information from the fetch_property response
            # The source is determined by the PropertyManager.fetch_property() method
            # which returns (property, source) where source indicates if it came from cache or fresh extraction
            source = getattr(fetch_property_response, 'source', 'unknown')
            specs = property_data.get("mls_info", {}).get("specs", {})
            bath = specs.get("bath")
            beds = specs.get("beds")
            living_size = specs.get("living_size")
            lot_size = specs.get("lot_size")
            
            logger.info(f"Property specs - beds: {beds}, bath: {bath}, living_size: {living_size}, lot_size: {lot_size}")
            
            sub_title = ""
            if beds:
                sub_title += f"{beds} BED "
            if bath:
                sub_title += f"{bath} BATH "
            if living_size:
                sub_title += f"{living_size} SF "
            if lot_size:
                sub_title += f"{lot_size} SF Lot "
            list_price = property_data.get("mls_info", {}).get("list_price")
            if list_price:
                sub_title += str(list_price) if str(list_price).startswith('$') else f"${list_price}"
            
            logger.info(f"Generated subtitle: '{sub_title}'")
            
            project_id = request.project_id if request.project_id else str(uuid.uuid4())
            project_name = property_data.get("address") or request.property_address
            property_id = fetch_property_response.property_details.id
            
            logger.info(f"Creating project - project_id: {project_id}, project_name: '{project_name}', property_id: {property_id}")
            
            project_manager = ProjectManager(user_id=user_id, project_id=project_id)
            project_manager.new_project(
                project_name=project_name,
                property_id=property_id
            )
            
            # Debug script retrieval
            script = property_data.get("script")
            logger.info(f"[PROPERTY_ACTIONS] Script from property_data: {script[:100] if script else 'None'}...")
            logger.info(f"[PROPERTY_ACTIONS] Property data keys: {list(property_data.keys())}")
            
            property_obj = {
                "project_id": project_id,
                "property_id": property_id,
                "name": project_name,
                "included_endtitle": True,
                "end_title": (property_data.get("address") or request.property_address).split(",")[0],
                "end_subtitle": sub_title,
                "included_ai_narration": True,
                "selected_ai_narration": script or "",
                "included_captions": False,
                "version": str(uuid.uuid4()),
            }
            
            logger.info(f"[PROPERTY_ACTIONS] Final script for video generation: {property_obj['selected_ai_narration'][:100] if property_obj['selected_ai_narration'] else 'None'}...")
            
            logger.success(f"Successfully completed fetch_property_details - User ID: {user_id}, Project ID: {property_obj['project_id']}, name: {property_obj['name']}, source: {source}")
            return FetchPropertyDetailsResponse(message="Property details fetched", property=property_obj, source=source)
        except Exception as e:
            logger.exception(f"Error in fetch_property_details for user_id: {user_id}, property_address: '{request.property_address}': {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        
        
    def fetch_property(self, request: FetchPropertyRequest, user_id: str = None) -> FetchPropertyResponse:        
        logger.info(f"Starting fetch_property for request_id: {request.request_id}, address: '{request.property_address}', input_type: {request.address_input_type}")
        if request.title:
            logger.info(f"Title provided: '{request.title}'")
        try:
            # Get user's tenant_id if user_id is provided
            tenant_id = "editora"  # Default tenant
            if user_id:
                logger.info(f"Fetching user data for user_id: {user_id} to get tenant information")
                from gcp.db import db_client
                from account.account_model import UserData
                
                user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(user_id)
                user_doc = user_ref.get()
                
                if user_doc.exists:
                    user_data = UserData.model_validate(user_doc.to_dict())
                    user_tenant_id = getattr(user_data, 'tenant_id', None)
                    if user_tenant_id:
                        tenant_id = user_tenant_id
                        logger.info(f"Using tenant_id '{tenant_id}' for user '{user_id}'")
                    else:
                        logger.info(f"User '{user_id}' has no tenant_id, using default tenant '{tenant_id}'")
                else:
                    logger.warning(f"User document not found for user_id: {user_id}, using default tenant '{tenant_id}'")
            else:
                logger.info(f"No user_id provided, using default tenant '{tenant_id}'")
            
            # Check if this is a title search for Jenna Cooper LA
            # Use title search when:
            # 1. address_input_type is PropertyTitle, OR
            # 2. title is provided and tenant is jenna_cooper_la
            use_title_search = (
                request.address_input_type == Address.AddressInputType.PropertyTitle or
                (request.title and tenant_id == "jenna_cooper_la")
            )
            
            if use_title_search and tenant_id == "jenna_cooper_la":
                logger.info(f"Title search detected for Jenna Cooper LA tenant")
                logger.info(f"Address input type: {request.address_input_type}")
                if request.title:
                    logger.info(f"Using provided title: '{request.title}'")
                else:
                    logger.info(f"Using property_address as title: '{request.property_address}'")
                
                property_mgr = PropertyManager(
                    address=request.property_address, 
                    tenant_id=tenant_id,
                    address_input_type=request.address_input_type,
                    title=request.title
                )
                
                # Use title search method with the appropriate title
                search_title = request.title if request.title else request.property_address
                property, source = property_mgr.search_by_title(search_title)
            else:
                # Regular address search
                logger.info(f"Creating PropertyManager for address: '{request.property_address}' with tenant_id: '{tenant_id}'")
                if request.title:
                    logger.info(f"Title provided for PropertyManager: '{request.title}'")
                property_mgr = PropertyManager(
                    address=request.property_address, 
                    tenant_id=tenant_id,
                    address_input_type=request.address_input_type,
                    title=request.title
                )
                
                logger.info(f"Calling PropertyManager.fetch_property() for address: '{request.property_address}'")
                property, source = property_mgr.fetch_property()
            
            if not property:
                logger.error(f"PropertyManager returned None for address: '{request.property_address}'")
                raise ValueError(f"Failed to extract property for address '{request.property_address}'")
            
            logger.success(f"PropertyManager successful for address: '{request.property_address}', property_id: {property.id}, source: {source}")
            
            response = FetchPropertyResponse(
                request_id=request.request_id,
                result=ActionStatus(state=ActionStatus.State.SUCCESS),
                last_updated=datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)),
                property_details=property
            )
            # Store source information in the response for later use
            response.source = source
            
            logger.info(f"Created successful FetchPropertyResponse for request_id: {request.request_id}")
            return response
            
        except (KeyError, ValueError) as kve:
            logger.error(f"KeyError/ValueError in fetch_property for request_id: {request.request_id}, address: '{request.property_address}': {str(kve)}")
            return FetchPropertyResponse(
                request_id=request.request_id,
                result=ActionStatus(state=ActionStatus.State.FAILURE, reason=str(kve)),
                last_updated=datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
            )
        except Exception as e:
            logger.exception(f"Unexpected error in fetch_property for request_id: {request.request_id}, address: '{request.property_address}': {str(e)}")
            return FetchPropertyResponse(
                request_id=request.request_id,
                result=ActionStatus(state=ActionStatus.State.FAILURE, reason=str(e)),
                last_updated=datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
            )
        finally:
            logger.info(f"Completed fetch_property for request_id: {request.request_id}")
            # Cleanup
            pass
