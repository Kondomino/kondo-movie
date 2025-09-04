from typing import Any

from google.cloud.firestore_v1.document import DocumentReference

from utils.common_models import Session
from config.config import settings
from gcp.db import db_client

def get_session_refs(session: Session) -> tuple[DocumentReference, DocumentReference, DocumentReference]:
    """
    Returns (user_ref, project_ref, version_ref) for a given Session.
    """
    user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(
        document_id=session.user.id
    )
    project_ref = user_ref.collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME).document(
        document_id=session.project.id
    )
    if session.version:
        version_ref = project_ref.collection(settings.GCP.Firestore.VERSIONS_COLLECTION_NAME).document(
            document_id=session.version.id
        )
    else:
        version_ref = None
        
    return user_ref, project_ref, version_ref

def get_session_refs_by_ids(user_id:str, project_id:str=None, version_id:str=None) -> tuple[DocumentReference, DocumentReference, DocumentReference]:
    """
    Returns (user_ref, project_ref, version_ref) for a given Session.
    """
    user_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME).document(
        document_id=user_id
    )
    
    project_ref, version_ref = None, None
    if project_id:
        project_ref = user_ref.collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME).document(
            document_id=project_id
        )
        if version_id:
            version_ref = project_ref.collection(settings.GCP.Firestore.VERSIONS_COLLECTION_NAME).document(
                document_id=version_id
            )
        
    return user_ref, project_ref, version_ref


def get_firestore_client():
    """
    Get Firestore client instance with proper credentials.
    Used by video classification manager to store scene classifications.
    Uses the existing db_client which is already configured with:
    - Project: editora-prod
    - Database: editora-v2
    - Credentials: editora-prod-f0da3484f1a0.json
    """
    from gcp.db import db_client
    return db_client
