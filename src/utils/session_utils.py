from typing import Any

from google.cloud.firestore_v1.document import DocumentReference

from utils.common_models import Session
from config.config import settings
from database.db_manager import unified_db_manager

def get_session_refs(session: Session) -> tuple[DocumentReference, DocumentReference, DocumentReference]:
    """
    Returns (user_ref, project_ref, version_ref) for a given Session.
    Updated to use unified database manager with backward compatibility.
    """
    # Delegate to unified session manager for database abstraction
    from services.session_service import unified_session_manager
    return unified_session_manager.get_session_refs_by_ids(
        session.user.id, 
        session.project.id if session.project else None,
        session.version.id if session.version else None
    )

def get_session_refs_by_ids(user_id:str, project_id:str=None, version_id:str=None) -> tuple[DocumentReference, DocumentReference, DocumentReference]:
    """
    Returns (user_ref, project_ref, version_ref) for a given Session.
    Updated to use unified database manager with backward compatibility.
    """
    # Delegate to unified session manager for database abstraction
    from services.session_service import unified_session_manager
    return unified_session_manager.get_session_refs_by_ids(user_id, project_id, version_id)


def get_firestore_client():
    """
    Get Firestore client instance with proper credentials.
    Updated to use unified database manager.
    Uses the existing configuration:
    - Project: editora-prod
    - Database: editora-v2
    - Credentials: editora-prod-f0da3484f1a0.json
    """
    return unified_db_manager.get_firestore_client()
