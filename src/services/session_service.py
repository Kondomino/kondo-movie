"""
Unified Session Service - Database-agnostic session and reference management.
Provides compatibility layer between Firestore DocumentReference pattern and PostgreSQL.
"""

from typing import Optional, Dict, Any, List, Tuple
from logger import logger
from database.db_manager import unified_db_manager
from services.project_service import project_service


class MockDocumentReference:
    """
    Mock DocumentReference that provides Firestore-like interface for PostgreSQL.
    Allows existing code to work without modification while using PostgreSQL backend.
    """
    
    def __init__(self, user_id: str, project_id: str = None, version_id: str = None, collection_name: str = None):
        self.user_id = user_id
        self.project_id = project_id
        self.version_id = version_id
        self.collection_name = collection_name
        self.id = project_id or version_id or user_id
        self.db_manager = unified_db_manager
        self.project_service = project_service
    
    def get(self):
        """Mock Firestore get() method"""
        return MockDocumentSnapshot(self.user_id, self.project_id, self.version_id, self.collection_name)
    
    def set(self, data: Dict[str, Any], merge: bool = False):
        """Mock Firestore set() method"""
        if self.collection_name == "projects" and self.project_id:
            if merge:
                self.project_service.update_project(self.user_id, self.project_id, data)
            else:
                self.project_service.create_project(self.user_id, self.project_id, data)
        else:
            logger.warning(f"[MOCK_DOC_REF] Unsupported set operation for collection: {self.collection_name}")
    
    def update(self, data: Dict[str, Any]):
        """Mock Firestore update() method"""
        if self.collection_name == "projects" and self.project_id:
            self.project_service.update_project(self.user_id, self.project_id, data)
        else:
            logger.warning(f"[MOCK_DOC_REF] Unsupported update operation for collection: {self.collection_name}")
    
    def collection(self, collection_name: str):
        """Mock Firestore collection() method"""
        return MockCollectionReference(self.user_id, self.project_id, collection_name)
    
    def document(self, document_id: str = None):
        """Mock Firestore document() method"""
        if self.collection_name == "projects":
            return MockDocumentReference(self.user_id, document_id, collection_name="projects")
        elif self.collection_name == "versions":
            return MockDocumentReference(self.user_id, self.project_id, document_id, collection_name="versions")
        else:
            return MockDocumentReference(self.user_id, document_id, collection_name=self.collection_name)


class MockDocumentSnapshot:
    """Mock Firestore DocumentSnapshot for PostgreSQL compatibility"""
    
    def __init__(self, user_id: str, project_id: str = None, version_id: str = None, collection_name: str = None):
        self.user_id = user_id
        self.project_id = project_id
        self.version_id = version_id
        self.collection_name = collection_name
        self.id = project_id or version_id or user_id
        self.project_service = project_service
    
    @property
    def exists(self) -> bool:
        """Mock Firestore exists property"""
        if self.collection_name == "projects" and self.project_id:
            return self.project_service.project_exists(self.user_id, self.project_id)
        return False
    
    def to_dict(self) -> Optional[Dict[str, Any]]:
        """Mock Firestore to_dict() method"""
        if self.collection_name == "projects" and self.project_id:
            return self.project_service.get_project(self.user_id, self.project_id)
        return None


class MockCollectionReference:
    """Mock Firestore CollectionReference for PostgreSQL compatibility"""
    
    def __init__(self, user_id: str, project_id: str = None, collection_name: str = None):
        self.user_id = user_id
        self.project_id = project_id
        self.collection_name = collection_name
        self.project_service = project_service
    
    def document(self, document_id: str = None):
        """Mock Firestore document() method"""
        if self.collection_name == "projects":
            return MockDocumentReference(self.user_id, document_id, collection_name="projects")
        elif self.collection_name == "versions":
            return MockDocumentReference(self.user_id, self.project_id, document_id, collection_name="versions")
        else:
            return MockDocumentReference(self.user_id, document_id, collection_name=self.collection_name)
    
    def stream(self):
        """Mock Firestore stream() method"""
        if self.collection_name == "projects":
            projects = self.project_service.get_user_projects(self.user_id, active_only=False)
            for project in projects:
                yield MockDocumentSnapshot(self.user_id, project['id'], collection_name="projects")
        else:
            logger.warning(f"[MOCK_COLLECTION_REF] Unsupported stream operation for collection: {self.collection_name}")
            return []
    
    def list_documents(self):
        """Mock Firestore list_documents() method"""
        if self.collection_name == "projects":
            projects = self.project_service.get_user_projects(self.user_id, active_only=False)
            return [MockDocumentReference(self.user_id, project['id'], collection_name="projects") for project in projects]
        else:
            logger.warning(f"[MOCK_COLLECTION_REF] Unsupported list_documents operation for collection: {self.collection_name}")
            return []


class UnifiedSessionManager:
    """
    Unified session manager that provides database-agnostic session handling.
    Provides both new clean interface and backward compatibility with existing Firestore code.
    """
    
    def __init__(self):
        self.db_manager = unified_db_manager
        self.project_service = project_service
    
    # New Clean Interface
    def get_project_data(self, user_id: str, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project data using clean interface"""
        return self.project_service.get_project(user_id, project_id)
    
    def create_project(self, user_id: str, project_id: str, project_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create project using clean interface"""
        return self.project_service.create_project(user_id, project_id, project_data)
    
    def update_project(self, user_id: str, project_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update project using clean interface"""
        return self.project_service.update_project(user_id, project_id, updates)
    
    def project_exists(self, user_id: str, project_id: str) -> bool:
        """Check if project exists using clean interface"""
        return self.project_service.project_exists(user_id, project_id)
    
    def get_user_projects(self, user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get user projects using clean interface"""
        return self.project_service.get_user_projects(user_id, active_only)
    
    # Backward Compatibility Interface (Firestore-style)
    def get_session_refs_by_ids(self, user_id: str, project_id: str = None, version_id: str = None):
        """
        Backward compatibility method that returns appropriate references.
        For PostgreSQL: Returns mock DocumentReference objects
        For Firestore: Returns real DocumentReference objects
        """
        if self.db_manager.is_postgresql_active():
            return self._get_mock_session_refs(user_id, project_id, version_id)
        else:
            return self._get_firestore_session_refs(user_id, project_id, version_id)
    
    def _get_mock_session_refs(self, user_id: str, project_id: str = None, version_id: str = None):
        """Get mock DocumentReference objects for PostgreSQL"""
        user_ref = MockDocumentReference(user_id, collection_name="users")
        
        project_ref = None
        if project_id:
            project_ref = MockDocumentReference(user_id, project_id, collection_name="projects")
        
        version_ref = None
        if version_id and project_id:
            version_ref = MockDocumentReference(user_id, project_id, version_id, collection_name="versions")
        
        return user_ref, project_ref, version_ref
    
    def _get_firestore_session_refs(self, user_id: str, project_id: str = None, version_id: str = None):
        """Get real Firestore DocumentReference objects"""
        from utils.session_utils import get_session_refs_by_ids as firestore_get_session_refs
        return firestore_get_session_refs(user_id, project_id, version_id)


# Global unified session manager instance
unified_session_manager = UnifiedSessionManager()


# Backward compatibility function - gradually migrate callers to use UnifiedSessionManager
def get_unified_session_refs_by_ids(user_id: str, project_id: str = None, version_id: str = None):
    """
    Unified session reference getter that works with both PostgreSQL and Firestore.
    This is a drop-in replacement for the original get_session_refs_by_ids function.
    """
    return unified_session_manager.get_session_refs_by_ids(user_id, project_id, version_id)
