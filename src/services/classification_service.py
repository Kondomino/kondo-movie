"""
Classification Storage Service - Database abstraction for classification results.
Provides unified interface for storing classification data in both PostgreSQL and Firestore.
"""

from typing import Dict, Any, Optional
from logger import logger
from database.db_manager import unified_db_manager
from services.project_service import project_service


class ClassificationStorageService:
    """
    Unified classification storage service that abstracts database operations.
    Stores classification results in a database-agnostic way.
    """
    
    def __init__(self):
        self.db_manager = unified_db_manager
        self.project_service = project_service
    
    def store_classification_results(self, user_id: str, project_id: str, results: Dict[str, Any]) -> bool:
        """Store classification results in the active database"""
        try:
            if self.db_manager.is_postgresql_active():
                return self._store_classification_postgresql(user_id, project_id, results)
            else:
                return self._store_classification_firestore(user_id, project_id, results)
        except Exception as e:
            logger.exception(f"[CLASSIFICATION_SERVICE] Failed to store classification results for project {project_id}: {e}")
            return False
    
    def get_classification_results(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get classification results from the active database"""
        try:
            if self.db_manager.is_postgresql_active():
                return self._get_classification_postgresql(user_id, project_id)
            else:
                return self._get_classification_firestore(user_id, project_id)
        except Exception as e:
            logger.exception(f"[CLASSIFICATION_SERVICE] Failed to get classification results for project {project_id}: {e}")
            return None
    
    def store_image_classification(self, user_id: str, project_id: str, image_buckets: Dict[str, Any]) -> bool:
        """Store image classification results"""
        from config.config import settings
        
        classification_data = {
            settings.Classification.IMAGE_CLASSIFICATION_KEY: image_buckets
        }
        return self.store_classification_results(user_id, project_id, classification_data)
    
    def store_video_classification(self, user_id: str, project_id: str, video_results: Dict[str, Any]) -> bool:
        """Store video classification results"""
        classification_data = {
            "video_classification": video_results
        }
        return self.store_classification_results(user_id, project_id, classification_data)
    
    def store_unified_classification(self, user_id: str, project_id: str, unified_results: Dict[str, Any]) -> bool:
        """Store unified classification results (mixed media)"""
        return self.store_classification_results(user_id, project_id, unified_results)
    
    def get_image_classification(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get image classification results"""
        from config.config import settings
        
        results = self.get_classification_results(user_id, project_id)
        if results:
            return results.get(settings.Classification.IMAGE_CLASSIFICATION_KEY)
        return None
    
    def get_video_classification(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get video classification results"""
        results = self.get_classification_results(user_id, project_id)
        if results:
            return results.get("video_classification")
        return None
    
    def classification_exists(self, user_id: str, project_id: str, classification_type: str = None) -> bool:
        """Check if classification results exist"""
        results = self.get_classification_results(user_id, project_id)
        if not results:
            return False
        
        if classification_type:
            return classification_type in results
        
        # Check if any classification data exists
        from config.config import settings
        classification_keys = [
            settings.Classification.IMAGE_CLASSIFICATION_KEY,
            "video_classification",
            "media_inventory",
            "unified_buckets"
        ]
        return any(key in results for key in classification_keys)
    
    # PostgreSQL Implementation
    def _store_classification_postgresql(self, user_id: str, project_id: str, results: Dict[str, Any]) -> bool:
        """Store classification results in PostgreSQL project metadata"""
        try:
            # Get current project data
            project_data = self.project_service.get_project(user_id, project_id)
            if not project_data:
                logger.warning(f"[CLASSIFICATION_SERVICE] Project {project_id} not found for classification storage")
                return False
            
            # Merge classification results with existing metadata
            current_metadata = project_data.get('metadata', {})
            
            # Store classification data in metadata
            if 'classification' not in current_metadata:
                current_metadata['classification'] = {}
            
            current_metadata['classification'].update(results)
            
            # Update project with new metadata
            updated_project = self.project_service.update_project(
                user_id, project_id, 
                {'metadata': current_metadata}
            )
            
            if updated_project:
                logger.info(f"[CLASSIFICATION_SERVICE] Stored classification results in PostgreSQL for project {project_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.exception(f"[CLASSIFICATION_SERVICE] Failed to store classification in PostgreSQL: {e}")
            return False
    
    def _get_classification_postgresql(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get classification results from PostgreSQL project metadata"""
        try:
            project_data = self.project_service.get_project(user_id, project_id)
            if project_data and 'metadata' in project_data:
                classification_data = project_data['metadata'].get('classification', {})
                if classification_data:
                    logger.debug(f"[CLASSIFICATION_SERVICE] Retrieved classification results from PostgreSQL for project {project_id}")
                    return classification_data
            return None
            
        except Exception as e:
            logger.exception(f"[CLASSIFICATION_SERVICE] Failed to get classification from PostgreSQL: {e}")
            return None
    
    # Firestore Implementation
    def _store_classification_firestore(self, user_id: str, project_id: str, results: Dict[str, Any]) -> bool:
        """Store classification results in Firestore"""
        try:
            from utils.session_utils import get_session_refs_by_ids
            
            user_ref, project_ref, _ = get_session_refs_by_ids(user_id, project_id)
            project_ref.set(results, merge=True)
            
            logger.info(f"[CLASSIFICATION_SERVICE] Stored classification results in Firestore for project {project_id}")
            return True
            
        except Exception as e:
            logger.exception(f"[CLASSIFICATION_SERVICE] Failed to store classification in Firestore: {e}")
            return False
    
    def _get_classification_firestore(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get classification results from Firestore"""
        try:
            from utils.session_utils import get_session_refs_by_ids
            
            user_ref, project_ref, _ = get_session_refs_by_ids(user_id, project_id)
            doc = project_ref.get()
            
            if doc.exists:
                project_data = doc.to_dict()
                logger.debug(f"[CLASSIFICATION_SERVICE] Retrieved classification results from Firestore for project {project_id}")
                return project_data
            
            return None
            
        except Exception as e:
            logger.exception(f"[CLASSIFICATION_SERVICE] Failed to get classification from Firestore: {e}")
            return None


# Global classification storage service instance
classification_storage_service = ClassificationStorageService()
