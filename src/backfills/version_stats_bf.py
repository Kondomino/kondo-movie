from rich import print
import re
import argparse

from google.cloud.firestore_v1.document import DocumentReference

from config.config import settings
from logger import logger
from gcp.db import db_client
from utils.session_utils import get_session_refs_by_ids
from utils.common_models import ActionStatus
from classification.classification_model import ImageBuckets

PROJECT_VERSION_STATS_KEY = 'version_stats'
PROJECT_VERSION_STATE_STATS_KEY = 'state'
PROJECT_VERSION_VIEWED_STATS_KEY = 'viewed'

def derive_version_stats(project_id:str, project_ref:DocumentReference)->str:
    if not project_id and not project_ref:
        raise ValueError("Project ID & document reference are required to derive property_id.")
    
    success_count = 0
    failure_count = 0
    pending_count = 0
    
    unviewed_count = 0
    
    versions_ref = project_ref.collection(settings.GCP.Firestore.VERSIONS_COLLECTION_NAME)
    count_query = versions_ref.count()
    try:
        for vdoc in versions_ref.stream():
            version = vdoc.to_dict()
            status = ActionStatus.model_validate(version.get('status'))
            if status.state == ActionStatus.State.SUCCESS:
                success_count += 1
                viewed = version.get('viewed', False)
                if not viewed:
                    unviewed_count += 1 
            elif status.state == ActionStatus.State.PENDING:
                pending_count += 1
            elif status.state == ActionStatus.State.FAILURE:
                failure_count += 1
        
        version_stats_dict = {
            PROJECT_VERSION_STATE_STATS_KEY : {
                'success': success_count,
                'failure': failure_count,
                'pending': pending_count    
            },
            PROJECT_VERSION_VIEWED_STATS_KEY : {
                'unviewed_count': unviewed_count
            }
        }
        return version_stats_dict
                
    except Exception as e:
        logger.exception(e)
        raise e
        
    
    return None

def backfill_project(project_id:str, project_ref:DocumentReference):
    version_stats = derive_version_stats(
        project_id=project_id,
        project_ref=project_ref
    )
    if version_stats:
        project_doc = project_ref.get()    
        if not project_doc.exists:
            raise ValueError(f"Project doesn't exist for ID {project_id}")
        project_dict = project_doc.to_dict()
        existing_version_stats = project_dict.get(PROJECT_VERSION_STATS_KEY, None)
        if existing_version_stats:
            logger.info(f'Project {project_id} - Version stats already exist. Overwriting')
        project_ref.update({PROJECT_VERSION_STATS_KEY:version_stats})
        logger.info(f'Project {project_id} - Added version stats')
    else:
        logger.info(f'Project {project_id} - Could not derive version stats')
    
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
    parser = argparse.ArgumentParser(description="Version Stats Backfiller")

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