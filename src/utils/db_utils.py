from google.cloud.firestore_v1.base_query import FieldFilter

from config.config import settings
from gcp.db import db_client
from project.project_backfill import *

def filter_active_projects(user_id: str)->dict:
    projects_with_versions = []
    projects_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME)\
        .document(user_id)\
        .collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME)
        
    # You can also apply filters on the projects if needed
    for project_doc in projects_ref.stream():
        project = project_doc.to_dict()
        if project.get('is_deleted'): 
            continue
        project_id = project_doc.id
        # Query the versions subcollection with a limit of 1 for efficiency
        versions_ref = projects_ref.document(project_id)\
            .collection(settings.GCP.Firestore.VERSIONS_COLLECTION_NAME)
        count_query = versions_ref.count()
        try:
            count_query_result = count_query.get()
            versions_count = count_query_result[0][0].value
            if versions_count:
                project[settings.GCP.Firestore.VERSIONS_COLLECTION_NAME] = []
                for vdoc in versions_ref.stream():
                    version = vdoc.to_dict()
                    project["versions"].append(version)
                projects_with_versions.append(project)
        except Exception as e:
            print(f"An error occurred: {e}")
                
    return projects_with_versions

def filter_active_projects_slim(user_id: str)->dict:
    try:
        projects_with_versions = []
        projects_ref = db_client.collection(settings.GCP.Firestore.USERS_COLLECTION_NAME)\
            .document(user_id)\
            .collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME)
            
        KEY_FILTERS = [
            "id",
            "name",
            "property_id",
            "music_rank",
            "is_deleted",
            PROJECT_VERSION_STATS_KEY,
            PROJECT_THUMBNAIL_INFO_KEY
        ]
        
        # You can also apply filters on the projects if needed
        for project_doc in projects_ref.select(KEY_FILTERS).stream():
            project_ref = project_doc.reference
            project_dict = project_doc.to_dict()
            if project_dict.get('is_deleted'): 
                continue
            
            version_stats = project_dict.get(PROJECT_VERSION_STATS_KEY, {})
            if not version_stats:
                logger.info(f"Version stats not found for project '{project_dict.get('id')}'. Backfilling")
                backfill_version_stats(project_ref=project_ref)
                project_dict = project_ref.get().to_dict()
                project_dict = {key: project_dict[key] for key in KEY_FILTERS if key in project_dict}
                version_stats = project_dict.get(PROJECT_VERSION_STATS_KEY, {})
            
            version_state_stats = version_stats.get(PROJECT_VERSION_STATE_STATS_KEY, {})
            success_count = version_state_stats.get('success', 0)
            pending_count = version_state_stats.get('pending', 0)
            if not (success_count + pending_count):
                continue
            
            version_active_stats = version_stats.get(PROJECT_VERSION_ACTIVE_STATS_KEY, {})
            active_count = version_active_stats.get('active_count', 0)
            if not active_count:
                continue
            
            thumbnail_info = project_dict.get(PROJECT_THUMBNAIL_INFO_KEY, {})
            if not thumbnail_info:
                logger.info(f"Thumbnail info not found for project '{project_dict.get('id')}'. Backfilling")
                backfill_thumbnail(project_ref=project_ref)
                project_dict = project_ref.get().to_dict()
                project_dict = {key: project_dict[key] for key in KEY_FILTERS if key in project_dict}
            
            projects_with_versions.append(project_dict)
    except Exception as e:
        print(f"An error occurred: {e}")
                
    return projects_with_versions