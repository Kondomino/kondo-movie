from rich import print
import re
import argparse
import time
import datetime as dt
from zoneinfo import ZoneInfo

from google.cloud.firestore_v1.document import DocumentReference

from config.config import settings
from logger import logger
from utils.session_utils import get_session_refs_by_ids
from classification.classification_model import ImageBuckets
from utils.common_models import ActionStatus

# Import StorageManager from GCP storage utilities
from gcp.storage import StorageManager

# Constant for version stats key
PROJECT_VERSION_STATS_KEY = 'version_stats'
PROJECT_VERSION_STATE_STATS_KEY = 'state'
PROJECT_VERSION_VIEWED_STATS_KEY = 'viewed'
PROJECT_VERSION_ACTIVE_STATS_KEY = 'active'
PROJECT_THUMBNAIL_INFO_KEY = 'thumbnail'
PROJECT_MEDIA_SIGNED_URLS_KEY = 'media_signed_urls'

# --- Property ID Backfill Functions ---
def derive_property_id(project_ref: DocumentReference) -> str:
    """
    Derives the property_id from the Firestore document by extracting the first occurrence of
    a gs:// URL from the 'editora-v2-properties' bucket in the image classification.

    Args:
        project_ref (DocumentReference): Firestore document reference.

    Returns:
        str: Derived property_id or None if not found.
    """
    if not project_ref:
        raise ValueError("Project ID & document reference are required to derive property_id.")

    project_dict = project_ref.get().to_dict()
    if settings.Classification.IMAGE_CLASSIFICATION_KEY not in project_dict.keys():
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

def backfill_property_id(project_ref: DocumentReference):
    """
    Backfills the property_id field for a project document if it has not already been set.
    """
    project_id = project_ref.id
    property_id = derive_property_id(project_ref)
    if property_id:
        project_doc = project_ref.get()
        if not project_doc.exists:
            raise ValueError(f"Project doesn't exist for ID {project_id}")
        project_dict = project_doc.to_dict()
        mapped_property_id = project_dict.get('property_id', None)
        if mapped_property_id:
            logger.info(f"Project {project_id} - Already mapped to property {mapped_property_id}. No-op")
            return
        project_ref.update({'property_id': property_id})
        logger.info(f"Project {project_id} - Mapped to property {property_id}")
    else:
        logger.info(f"Project {project_id} - Could not derive Property ID")

def backfill_property_id_for_project(user_id: str, project_id: str = None):
    """
    Backfills property_id for a single project (if project_id is provided) or for all projects for a user.
    """
    try:
        if project_id:
            user_ref, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            backfill_property_id(project_ref)
        else:
            user_ref, _, _ = get_session_refs_by_ids(user_id=user_id)
            for project_ref in user_ref.collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME).list_documents():
                project_doc = project_ref.get()
                if project_doc.exists and not project_doc.to_dict().get('is_deleted', False):
                    backfill_property_id(project_ref)
                else:
                    logger.warning(f"Project {project_ref.id} does not exist or is deleted")
    except Exception as e:
        logger.exception(e)
    

# --- Version Stats Backfill Functions ---
def derive_version_stats(project_ref: DocumentReference):
    """
    Derives version statistics from the project’s versions subcollection.
    Counts the number of successes, failures, pending items, and unviewed successes.

    Args:
        project_ref (DocumentReference): Firestore document reference.

    Returns:
        dict: Dictionary containing version stats.
    """
    if not project_ref:
        raise ValueError("Project ID & document reference are required to derive version stats.")

    success_count = 0
    failure_count = 0
    pending_count = 0
    unviewed_count = 0
    active_count = 0
    deleted_count = 0

    versions_ref = project_ref.collection(settings.GCP.Firestore.VERSIONS_COLLECTION_NAME)
    try:
        for vdoc in versions_ref.stream():
            version = vdoc.to_dict()
            
            if version.get('is_deleted', False):
                deleted_count += 1
            else:
                active_count += 1
                
            status = ActionStatus.model_validate(version.get('status'))
            if status.state == ActionStatus.State.SUCCESS:
                success_count += 1
                viewed = version.get('viewed', False)
                if not viewed and not version.get('is_deleted', False):
                    unviewed_count += 1 
            elif status.state == ActionStatus.State.PENDING:
                pending_count += 1
            elif status.state == ActionStatus.State.FAILURE:
                failure_count += 1

        version_stats_dict = {
            PROJECT_VERSION_STATE_STATS_KEY: {
                'success': success_count,
                'failure': failure_count,
                'pending': pending_count    
            },
            PROJECT_VERSION_VIEWED_STATS_KEY: {
                'unviewed_count': unviewed_count
            },
            PROJECT_VERSION_ACTIVE_STATS_KEY: {
                'active_count': active_count,
                'deleted_count': deleted_count
            }
        }
        return version_stats_dict
    except Exception as e:
        logger.exception(e)
        raise e

def backfill_version_stats(project_ref: DocumentReference):
    """
    Backfills the version_stats field for a project document.
    Always overwrites the version_stats field.
    """
    project_id = project_ref.id
    version_stats = derive_version_stats(project_ref)
    if version_stats:
        project_doc = project_ref.get()
        if not project_doc.exists:
            raise ValueError(f"Project doesn't exist for ID {project_id}")
        project_dict = project_doc.to_dict()
        existing_version_stats = project_dict.get(PROJECT_VERSION_STATS_KEY, None)
        if existing_version_stats:
            logger.info(f"Project {project_id} - Version stats already exist. Overwriting")
        project_ref.update({PROJECT_VERSION_STATS_KEY: version_stats})
        logger.info(f"Project {project_id} - Added version stats")
    else:
        logger.info(f"Project {project_id} - Could not derive version stats")

def backfill_version_stats_for_project(user_id: str, project_id: str = None):
    """
    Backfills version stats for a single project (if project_id is provided) or for all projects for a user.
    """
    try:
        if project_id:
            user_ref, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            backfill_version_stats(project_ref)
        else:
            user_ref, _, _ = get_session_refs_by_ids(user_id=user_id)
            for project_ref in user_ref.collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME).list_documents():
                project_doc = project_ref.get()
                if project_doc.exists and not project_doc.to_dict().get('is_deleted', False):
                    backfill_version_stats(project_ref)
                else:
                    logger.warning(f"Project {project_ref.id} does not exist or is deleted")
    except Exception as e:
        logger.exception(e)
    

# --- Thumbnail Backfill Functions ---
def gen_thumbnail_info(gs_url:str, created_at:dt.datetime):
    gs_url = gs_url
    signed_url = StorageManager.generate_signed_url_from_gs_url(gs_url)
    current_time = dt.datetime.now(tz=ZoneInfo(settings.General.TIMEZONE))
    expiry_delta = dt.timedelta(hours=settings.Authentication.SignedURL.GET_EXPIRY_IN_HOURS)
    signature_expiry = current_time + expiry_delta 

    return {
        "gs_url": gs_url,
        "created_at": created_at,
        "signed_url": signed_url,
        "signature_expiry": signature_expiry
    }
    
def derive_thumbnail(project_ref: DocumentReference) -> dict:
    """
    Derives the thumbnail details from the last version (i.e., the one with the most recent
    created timestamp) that has a SUCCESS state. The thumbnail is created from the first image
    in the used_images list of that version's story.
    
    Returns a dict with the following keys:
      - gs_url: The original Google Storage URL of the thumbnail image.
      - signed_url: A signed URL generated from the gs_url.
      - signature_expiry: Time when signature expires.
    """
    versions_ref = project_ref.collection(settings.GCP.Firestore.VERSIONS_COLLECTION_NAME)
    latest_successful_version = None
    latest_timestamp = None
    
    for vdoc in versions_ref.stream():
        version = vdoc.to_dict()
        try:
            status = ActionStatus.model_validate(version.get('status'))
        except Exception:
            continue  # Skip if status validation fails
        if status.state == ActionStatus.State.SUCCESS:
            # Assume creation time is stored under version["time"]["created"]
            created_at = version.get("time", {}).get("created")
            if created_at is not None:
                if latest_timestamp is None or created_at > latest_timestamp:
                    # Ensure this version has a story with used_images
                    story = version.get("story", {})
                    used_images = story.get("used_images", [])
                    if used_images:
                        latest_successful_version = version
                        latest_timestamp = created_at

    if not latest_successful_version:
        return None

    # Derive the thumbnail from the latest successful version's story.
    story = latest_successful_version.get("story", {})
    used_images = story.get("used_images", [])
    if not used_images:
        return None

    return gen_thumbnail_info(
        gs_url=used_images[0],
        created_at=created_at
    )

def backfill_thumbnail(project_ref: DocumentReference):
    """
    Backfills the 'thumbnail' field for a project document if it has not already been set.
    """
    project_id = project_ref.id
    thumbnail = derive_thumbnail(project_ref)
    if thumbnail:
        project_doc = project_ref.get()
        if not project_doc.exists:
            raise ValueError(f"Project doesn't exist for ID {project_id}")
        project_dict = project_doc.to_dict()
        existing_thumbnail = project_dict.get(PROJECT_THUMBNAIL_INFO_KEY, None)
        if existing_thumbnail:
            logger.info(f"Project {project_id} - Thumbnail already exists. Overwriting it")
        project_ref.update({PROJECT_THUMBNAIL_INFO_KEY: thumbnail})
        logger.info(f"Project {project_id} - Thumbnail backfilled successfully")
    else:
        logger.info(f"Project {project_id} - Could not derive thumbnail")

def backfill_thumbnail_for_project(user_id: str, project_id: str = None):
    """
    Backfills the thumbnail for a single project (if project_id is provided)
    or for all projects for a user.
    """
    try:
        if project_id:
            user_ref, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            backfill_thumbnail(project_ref)
        else:
            user_ref, _, _ = get_session_refs_by_ids(user_id=user_id)
            for project_ref in user_ref.collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME).list_documents():
                project_doc = project_ref.get()
                if project_doc.exists and not project_doc.to_dict().get('is_deleted', False):
                    backfill_thumbnail(project_ref)
                else:
                    logger.warning(f"Project {project_ref.id} does not exist or is deleted")
    except Exception as e:
        logger.exception(e)
    
            
# --- Project Images Backfill Functions ---
def gen_signed_urls(user_id: str, project_ref: DocumentReference) -> tuple:
    """
    Generates signed URLs for all media (images and videos) tied to the project
    Following ADR-001 conventions for asset organization
    
    Returns a tuple of:
      - List of dicts with keys: file_name, gs_url, signed_url
      - Global signature expiry timestamp
    """
    project_doc = project_ref.get()
    if not project_doc.exists:
        logger.warning(f"Project doesn't exist for user '{user_id}' and project '{project_ref.id}'")
        return [], None
        
    project_dict = project_doc.to_dict()
    excluded_images = project_dict.get("excluded_images", [])
    
    # Ensure property_id is backfilled for image repos
    property_id = project_dict.get("property_id", None)
    if not property_id:
        backfill_property_id_for_project(
            user_id=user_id,
            project_id=project_ref.id
        )
    
    all_signed_urls = []
    global_signature_expiry = None
    
    # Get all media repositories
    media_repos = StorageManager.get_all_media_repos_for_project(
        user_id=user_id, 
        project_id=project_ref.id
    )
    
    # Process image repositories
    image_file_types = ['.jpg', '.jpeg', '.png', '.webp', '.avif']
    for repo in media_repos['images']:
        try:
            urls, expiry = StorageManager.gen_signed_urls_for_bucket(
                repo, excluded_images, image_file_types
            )
            all_signed_urls.extend(urls)
            if not global_signature_expiry and expiry:
                global_signature_expiry = expiry
        except Exception as e:
            logger.warning(f"Failed to generate signed URLs for image repo {repo}: {e}")
    
    # Process video repositories  
    video_file_types = ['.mp4', '.mov', '.webm', '.m4v']
    for repo in media_repos['videos']:
        try:
            urls, expiry = StorageManager.gen_signed_urls_for_bucket(
                repo, [], video_file_types  # No excluded videos yet
            )
            all_signed_urls.extend(urls)
            if not global_signature_expiry and expiry:
                global_signature_expiry = expiry
        except Exception as e:
            logger.warning(f"Failed to generate signed URLs for video repo {repo}: {e}")
    
    logger.info(f"Generated {len(all_signed_urls)} signed URLs for project {project_ref.id} "
               f"({len([u for u in all_signed_urls if any(u['file_name'].endswith(ext) for ext in image_file_types)])} images, "
               f"{len([u for u in all_signed_urls if any(u['file_name'].endswith(ext) for ext in video_file_types)])} videos)")
    
    return all_signed_urls, global_signature_expiry

def backfill_media_signed_urls(user_id: str, project_ref: DocumentReference, force: bool = False):
    """
    Backfills the signed URLs for all media files for the project.
    Following ADR-001 conventions, stores images and videos separately for backward compatibility.
    
    If force is True, new signed URLs are generated regardless of current values.
    Otherwise, if the global 'signature_expiry' has passed, all URLs are regenerated.
    
    The project document stores:
    - media_signed_urls: { media: [...images...], signature_expiry: ... } (backward compatible)
    - video_signed_urls: { media: [...videos...], signature_expiry: ... } (new)
    """
    project_id = project_ref.id
    
    # Retrieve the current project document
    project_doc = project_ref.get()
    if not project_doc.exists:
        raise ValueError(f"Project doesn't exist for ID {project_id}")
    project_dict = project_doc.to_dict()
    
    # Check if we need to regenerate URLs
    should_regenerate = force
    if not should_regenerate:
        # Check existing image URLs expiry
        existing_image_data = project_dict.get(PROJECT_MEDIA_SIGNED_URLS_KEY, {})
        existing_video_data = project_dict.get("video_signed_urls", {})
        
        current_timestamp = time.time()
        
        # Check if either image or video URLs have expired
        for data_key, data in [("images", existing_image_data), ("videos", existing_video_data)]:
            if data:
                expiry = data.get("signature_expiry")
                if expiry and expiry.timestamp() < current_timestamp:
                    logger.info(f"Project {project_id} - {data_key} signature_expiry has passed. Regenerating signed URLs.")
                    should_regenerate = True
                    break
        
        if not should_regenerate:
            logger.debug(f"Project {project_id} - Media signed URLs are still valid. Skipping backfill.")
            return
    
    # Generate new signed URLs for all media
    all_signed_urls, signature_expiry = gen_signed_urls(user_id=user_id, project_ref=project_ref)
    
    # Separate URLs by type
    image_file_types = ['.jpg', '.jpeg', '.png', '.webp', '.avif']
    video_file_types = ['.mp4', '.mov', '.webm', '.m4v']
    
    image_urls = [url for url in all_signed_urls 
                 if any(url['file_name'].lower().endswith(ext) for ext in image_file_types)]
    video_urls = [url for url in all_signed_urls 
                 if any(url['file_name'].lower().endswith(ext) for ext in video_file_types)]
    
    # Prepare updates
    updates = {}
    
    # Update image URLs (backward compatible)
    image_data = {
        "media": image_urls,
        "signature_expiry": signature_expiry
    }
    updates[PROJECT_MEDIA_SIGNED_URLS_KEY] = image_data
    
    # Update video URLs (new)
    if video_urls or force:  # Only create video_signed_urls if we have videos or forcing
        video_data = {
            "media": video_urls,
            "signature_expiry": signature_expiry
        }
        updates["video_signed_urls"] = video_data
    
    # Apply updates
    if updates:
        project_ref.update(updates)
        logger.info(f"Project {project_id} - Media signed URLs backfilled successfully: "
                   f"{len(image_urls)} images, {len(video_urls)} videos")
    else:
        logger.info(f"Project {project_id} - No media found to backfill")

def backfill_media_signed_urls_for_project(user_id: str, project_id: str = None, force: bool = False):
    """
    Backfills the thumbnail for a single project (if project_id is provided)
    or for all projects for a user.
    """
    try:
        if project_id:
            user_ref, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            backfill_media_signed_urls(user_id, project_ref, force=force)
        else:
            user_ref, _, _ = get_session_refs_by_ids(user_id=user_id)
            for project_ref in user_ref.collection(settings.GCP.Firestore.PROJECTS_COLLECTION_NAME).list_documents():
                project_doc = project_ref.get()
                if project_doc.exists and not project_doc.to_dict().get('is_deleted', False):
                    backfill_media_signed_urls(user_id, project_ref, force=force)
                else:
                    logger.warning(f"Project {project_ref.id} does not exist or is deleted")
    except Exception as e:
        logger.exception(e)
    

# --- Main Entry Point ---
def main():
    """
    Command-line entry point.
    Usage:
      -u / --user_id: User ID
      -p / --project_id: Project ID (or 'all' for all projects)
      -t / --type: Backfill type: "property" for property_id, "version" for version_stats, or "thumbnail" for thumbnail backfill.
    """
    parser = argparse.ArgumentParser(description="Project Backfiller")
    parser.add_argument("-u", "--user_id", type=str, required=True, help="User ID")
    parser.add_argument("-p", "--project_id", type=str, required=True, help="Project ID or 'all'")
    parser.add_argument("-t", "--type", type=str, required=True, choices=["property", "version", "thumbnail", "sign", "all"],
                        help="Type of backfill: 'property' for property_id, 'version' for version_stats, or 'thumbnail' for thumbnail backfill")
    parser.add_argument("-f", "--force", action="store_true", help="Force backfill")
    
    args = parser.parse_args()
    
    if args.type == "property":
        backfill_property_id_for_project(
            user_id=args.user_id,
            project_id=args.project_id if args.project_id != 'all' else None
        )
    elif args.type == "version":
        backfill_version_stats_for_project(
            user_id=args.user_id,
            project_id=args.project_id if args.project_id != 'all' else None
        )
    elif args.type == "thumbnail":
        backfill_thumbnail_for_project(
            user_id=args.user_id,
            project_id=args.project_id if args.project_id != 'all' else None
        )
    elif args.type == "sign":
        backfill_media_signed_urls_for_project(
            user_id=args.user_id,
            project_id=args.project_id if args.project_id != 'all' else None,
            force=args.force
        )
    elif args.type == "all":
        backfill_property_id_for_project(
            user_id=args.user_id,
            project_id=args.project_id if args.project_id != 'all' else None
        )
        backfill_version_stats_for_project(
            user_id=args.user_id,
            project_id=args.project_id if args.project_id != 'all' else None
        )
        backfill_thumbnail_for_project(
            user_id=args.user_id,
            project_id=args.project_id if args.project_id != 'all' else None
        )
        backfill_media_signed_urls_for_project(
            user_id=args.user_id,
            project_id=args.project_id if args.project_id != 'all' else None,
            force=args.force
        )
        
if __name__ == '__main__':
    main()
