"""
Unified Session Utils - Database-agnostic replacement for session_utils.py
Provides backward compatibility while supporting both PostgreSQL and Firestore.
"""

from typing import Any, Optional
from services.session_service import unified_session_manager
from utils.common_models import Session


def get_session_refs(session: Session):
    """
    Database-agnostic replacement for original get_session_refs function.
    Returns appropriate references based on active database provider.
    """
    return unified_session_manager.get_session_refs_by_ids(
        session.user.id, 
        session.project.id if session.project else None,
        session.version.id if session.version else None
    )


def get_session_refs_by_ids(user_id: str, project_id: str = None, version_id: str = None):
    """
    Database-agnostic replacement for original get_session_refs_by_ids function.
    This is a drop-in replacement that works with both PostgreSQL and Firestore.
    """
    return unified_session_manager.get_session_refs_by_ids(user_id, project_id, version_id)


def get_firestore_client():
    """
    Get Firestore client instance with proper credentials.
    Updated to work with unified database manager.
    """
    from database.db_manager import unified_db_manager
    return unified_db_manager.get_firestore_client()


# Additional helper functions for clean interface
def get_project_data(user_id: str, project_id: str) -> Optional[dict]:
    """Get project data using clean interface"""
    return unified_session_manager.get_project_data(user_id, project_id)


def create_project(user_id: str, project_id: str, project_data: dict) -> Optional[dict]:
    """Create project using clean interface"""
    return unified_session_manager.create_project(user_id, project_id, project_data)


def update_project(user_id: str, project_id: str, updates: dict) -> Optional[dict]:
    """Update project using clean interface"""
    return unified_session_manager.update_project(user_id, project_id, updates)


def project_exists(user_id: str, project_id: str) -> bool:
    """Check if project exists using clean interface"""
    return unified_session_manager.project_exists(user_id, project_id)


def get_user_projects(user_id: str, active_only: bool = True) -> list:
    """Get user projects using clean interface"""
    return unified_session_manager.get_user_projects(user_id, active_only)
