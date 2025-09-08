"""
Project Service - Database abstraction layer for project operations.
Provides unified interface that works with both PostgreSQL and Firestore.
"""

from typing import Optional, Dict, Any, List
from logger import logger
from database.db_manager import unified_db_manager
from database.repository.project_repository import ProjectRepository, ProjectVersionRepository


class ProjectService:
    """
    Unified project service that abstracts database operations.
    Automatically switches between PostgreSQL and Firestore based on configuration.
    """
    
    def __init__(self):
        self.db_manager = unified_db_manager
    
    def create_project(self, user_id: str, project_id: str, project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new project in the active database"""
        try:
            if self.db_manager.is_postgresql_active():
                return self._create_project_postgresql(user_id, project_id, project_data)
            else:
                return self._create_project_firestore(user_id, project_id, project_data)
        except Exception as e:
            logger.exception(f"[PROJECT_SERVICE] Failed to create project {project_id}: {e}")
            return None
    
    def get_project(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project data from the active database"""
        try:
            if self.db_manager.is_postgresql_active():
                return self._get_project_postgresql(user_id, project_id)
            else:
                return self._get_project_firestore(user_id, project_id)
        except Exception as e:
            logger.exception(f"[PROJECT_SERVICE] Failed to get project {project_id}: {e}")
            return None
    
    def update_project(self, user_id: str, project_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update project data in the active database"""
        try:
            if self.db_manager.is_postgresql_active():
                return self._update_project_postgresql(user_id, project_id, updates)
            else:
                return self._update_project_firestore(user_id, project_id, updates)
        except Exception as e:
            logger.exception(f"[PROJECT_SERVICE] Failed to update project {project_id}: {e}")
            return None
    
    def project_exists(self, user_id: str, project_id: str) -> bool:
        """Check if project exists in the active database"""
        try:
            if self.db_manager.is_postgresql_active():
                return self._project_exists_postgresql(user_id, project_id)
            else:
                return self._project_exists_firestore(user_id, project_id)
        except Exception as e:
            logger.exception(f"[PROJECT_SERVICE] Failed to check project existence {project_id}: {e}")
            return False
    
    def get_user_projects(self, user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all projects for a user from the active database"""
        try:
            if self.db_manager.is_postgresql_active():
                return self._get_user_projects_postgresql(user_id, active_only)
            else:
                return self._get_user_projects_firestore(user_id, active_only)
        except Exception as e:
            logger.exception(f"[PROJECT_SERVICE] Failed to get projects for user {user_id}: {e}")
            return []
    
    # PostgreSQL Implementation Methods
    def _create_project_postgresql(self, user_id: str, project_id: str, project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create project in PostgreSQL"""
        with self.db_manager.get_session() as session:
            if not session:
                logger.error("[PROJECT_SERVICE] PostgreSQL session is None")
                return None
                
            repo = ProjectRepository(session)
            
            # Convert Firestore-style data to PostgreSQL model fields
            pg_data = {
                'id': project_id,
                'user_id': user_id,
                'name': project_data.get('name'),
                'description': project_data.get('description'),
                'status': project_data.get('status', 'active'),
                'settings': project_data.get('settings', {}),
                'template_id': project_data.get('template_id'),
                'style_preferences': project_data.get('style_preferences', {}),
                'metadata': {
                    'property_id': project_data.get('property_id'),
                    'excluded_images': project_data.get('excluded_images', []),
                    # Store any additional Firestore fields in metadata
                    **{k: v for k, v in project_data.items() 
                       if k not in ['name', 'description', 'status', 'settings', 'template_id', 'style_preferences', 'property_id', 'excluded_images']}
                }
            }
            
            project = repo.create(**pg_data)
            if project:
                logger.info(f"[PROJECT_SERVICE] Created project {project_id} in PostgreSQL")
                return project.to_dict()
            return None
    
    def _get_project_postgresql(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project from PostgreSQL"""
        with self.db_manager.get_session() as session:
            if not session:
                return None
                
            repo = ProjectRepository(session)
            projects = repo.get_by_filter(user_id=user_id, id=project_id)
            
            if projects:
                project = projects[0]
                # Convert PostgreSQL model back to Firestore-compatible format
                project_dict = project.to_dict()
                
                # Flatten metadata back to top level for compatibility
                if project_dict.get('metadata'):
                    metadata = project_dict.pop('metadata')
                    project_dict.update(metadata)
                
                logger.debug(f"[PROJECT_SERVICE] Retrieved project {project_id} from PostgreSQL")
                return project_dict
            return None
    
    def _update_project_postgresql(self, user_id: str, project_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update project in PostgreSQL"""
        with self.db_manager.get_session() as session:
            if not session:
                return None
                
            repo = ProjectRepository(session)
            projects = repo.get_by_filter(user_id=user_id, id=project_id)
            
            if not projects:
                logger.warning(f"[PROJECT_SERVICE] Project {project_id} not found for update")
                return None
            
            project = projects[0]
            
            # Handle metadata updates - merge with existing metadata
            if 'metadata' in updates:
                current_metadata = project.metadata or {}
                current_metadata.update(updates['metadata'])
                updates['metadata'] = current_metadata
            else:
                # Handle top-level updates that should go to metadata
                metadata_fields = ['property_id', 'excluded_images', 'media_signed_urls', 'thumbnail', 'version_stats']
                metadata_updates = {}
                for field in metadata_fields:
                    if field in updates:
                        metadata_updates[field] = updates.pop(field)
                
                if metadata_updates:
                    current_metadata = project.metadata or {}
                    current_metadata.update(metadata_updates)
                    updates['metadata'] = current_metadata
            
            updated_project = repo.update(project.id, **updates)
            if updated_project:
                logger.info(f"[PROJECT_SERVICE] Updated project {project_id} in PostgreSQL")
                return updated_project.to_dict()
            return None
    
    def _project_exists_postgresql(self, user_id: str, project_id: str) -> bool:
        """Check if project exists in PostgreSQL"""
        with self.db_manager.get_session() as session:
            if not session:
                return False
                
            repo = ProjectRepository(session)
            projects = repo.get_by_filter(user_id=user_id, id=project_id)
            return len(projects) > 0
    
    def _get_user_projects_postgresql(self, user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get user projects from PostgreSQL"""
        with self.db_manager.get_session() as session:
            if not session:
                return []
                
            repo = ProjectRepository(session)
            
            if active_only:
                projects = repo.get_active_projects(user_id)
            else:
                projects = repo.get_by_user_id(user_id)
            
            # Convert to Firestore-compatible format
            result = []
            for project in projects:
                project_dict = project.to_dict()
                # Flatten metadata
                if project_dict.get('metadata'):
                    metadata = project_dict.pop('metadata')
                    project_dict.update(metadata)
                result.append(project_dict)
            
            logger.debug(f"[PROJECT_SERVICE] Retrieved {len(result)} projects for user {user_id} from PostgreSQL")
            return result
    
    # Firestore Implementation Methods
    def _create_project_firestore(self, user_id: str, project_id: str, project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create project in Firestore"""
        from utils.session_utils import get_session_refs_by_ids
        
        user_ref, project_ref, _ = get_session_refs_by_ids(user_id, project_id)
        project_ref.set(project_data)
        logger.info(f"[PROJECT_SERVICE] Created project {project_id} in Firestore")
        return project_data
    
    def _get_project_firestore(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project from Firestore"""
        from utils.session_utils import get_session_refs_by_ids
        
        user_ref, project_ref, _ = get_session_refs_by_ids(user_id, project_id)
        doc = project_ref.get()
        if doc.exists:
            logger.debug(f"[PROJECT_SERVICE] Retrieved project {project_id} from Firestore")
            return doc.to_dict()
        return None
    
    def _update_project_firestore(self, user_id: str, project_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update project in Firestore"""
        from utils.session_utils import get_session_refs_by_ids
        
        user_ref, project_ref, _ = get_session_refs_by_ids(user_id, project_id)
        project_ref.set(updates, merge=True)
        logger.info(f"[PROJECT_SERVICE] Updated project {project_id} in Firestore")
        
        # Return updated data
        doc = project_ref.get()
        return doc.to_dict() if doc.exists else None
    
    def _project_exists_firestore(self, user_id: str, project_id: str) -> bool:
        """Check if project exists in Firestore"""
        from utils.session_utils import get_session_refs_by_ids
        
        user_ref, project_ref, _ = get_session_refs_by_ids(user_id, project_id)
        return project_ref.get().exists
    
    def _get_user_projects_firestore(self, user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get user projects from Firestore"""
        from utils.session_utils import get_session_refs_by_ids
        from config.config import settings
        
        user_ref, _, _ = get_session_refs_by_ids(user_id)
        projects_ref = user_ref.collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME)
        
        projects = []
        for project_doc in projects_ref.stream():
            project_data = project_doc.to_dict()
            if active_only and project_data.get('is_deleted'):
                continue
            if not active_only or not project_data.get('is_deleted'):
                project_data['id'] = project_doc.id
                projects.append(project_data)
        
        logger.debug(f"[PROJECT_SERVICE] Retrieved {len(projects)} projects for user {user_id} from Firestore")
        return projects


# Global project service instance
project_service = ProjectService()
