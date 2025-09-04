from rich import print
import re
import argparse

from google.cloud.firestore_v1.document import DocumentReference

from config.config import settings
from logger import logger
from gcp.db import db_client
from utils.session_utils import get_session_refs_by_ids
from classification.classification_model import ImageBuckets

def derive_property_id(project_id:str, project_ref:DocumentReference)->str:
    """
    Derives the property_id from the Firestore document by extracting the first occurrence of
    a gs:// URL from the 'editora-v2-properties' bucket in the image classification.

    Args:
        project_id (str): The project ID.
        project_ref (DocumentReference, optional): Firestore document reference.

    Returns:
        str: Derived property_id or None if not found.
    """

    if not project_id and not project_ref:
        raise ValueError("Project ID & document reference are required to derive property_id.")

    project_dict = project_ref.get().to_dict()
    
    if not settings.Classification.IMAGE_CLASSIFICATION_KEY in project_dict.keys():
        return None
    
    buckets = ImageBuckets.model_validate(project_dict[settings.Classification.IMAGE_CLASSIFICATION_KEY])
    for category, items in buckets.buckets.items():
        for item in items:
            gs_bucket = f"gs://{settings.GCP.Storage.PROPERTIES_BUCKET}"
            if gs_bucket in item.uri:
                match = re.search(rf'{gs_bucket}/(.*?)/', item.uri)
                if match:
                    return match.group(1)
    
    return None

def backfill_project(project_id:str, project_ref:DocumentReference):
    property_id = derive_property_id(
        project_id=project_id,
        project_ref=project_ref
    )
    if property_id:
        project_doc = project_ref.get()    
        if not project_doc.exists:
            raise ValueError(f"Project doesn't exist for ID {project_id}")
        project_dict = project_doc.to_dict()
        mapped_property_id = project_dict.get('property_id', None)
        if mapped_property_id:
            logger.info(f'Project {project_id} - Already mapped to property {property_id}. No-op')
            return
        project_ref.update({'property_id':property_id})
        logger.info(f'Project {project_id} - Mapped to property {property_id}')
    else:
        logger.info(f'Project {project_id} - Could not derive Property ID')
    
def backfill_projects_for_user(user_id:str, project_id:str=None):
    if project_id:
        user_ref, project_ref, _ = get_session_refs_by_ids(
            user_id=user_id,
            project_id=project_id
        )
        backfill_project(
            project_id=project_id,
            project_ref=project_ref
        )
    else: # All projects
        user_ref, _, _ = get_session_refs_by_ids(
            user_id=user_id,
        )
        for project_ref in user_ref.collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME).list_documents():
            backfill_project(
                project_id=project_ref.id,
                project_ref=project_ref
            )

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Property ID Backfiller")

    # Create a mutually exclusive group to ensure user chooses either file or directory mode, not both
    parser.add_argument("-u", "--user_id", type=str, required=True, help="User ID")
    parser.add_argument("-p", "--project_id", type=str, required=True, help="Project ID")
    
    args = parser.parse_args()
    
    backfill_projects_for_user(
        user_id=args.user_id,
        project_id=args.project_id \
            if args.project_id != 'all' \
                else None
    )
    
if __name__ == '__main__':
    main()