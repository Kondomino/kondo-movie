import os
from typing import List, Optional, Dict, Any
from pathlib import Path
from logger import logger
from config.config import settings
from gcp.storage import StorageManager
from gcp.storage_model import CloudPath
from classification.types.media_models import (
    MediaType, MediaInventory, ImageMedia, VideoMedia, SceneClipMedia
)


class MediaTypeDetector:
    """Service to detect and categorize media types in project storage"""
    
    # Define supported file extensions
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.avif', '.bmp', '.tiff'}
    VIDEO_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.3gp'}
    
    def __init__(self):
        pass
    
    def analyze_project_media(self, user_id: str, project_id: str) -> MediaInventory:
        """
        Scan project storage and categorize all media types
        
        Args:
            user_id: User ID
            project_id: Project ID
            
        Returns:
            MediaInventory with categorized media
        """
        logger.info(f"[MEDIA_DETECTOR] Analyzing media for project {project_id}")
        
        try:
            # Get all media paths from storage
            all_media_paths = self._get_all_project_media_paths(user_id, project_id)
            
            if not all_media_paths:
                logger.info(f"[MEDIA_DETECTOR] No media found for project {project_id}")
                return MediaInventory()
            
            # Categorize media by type
            images = []
            videos = []
            scene_clips = []
            categorization_errors = 0
            
            for media_path in all_media_paths:
                try:
                    media_type = self.detect_media_type(media_path)
                    
                    if media_type == MediaType.IMAGE:
                        images.append(ImageMedia(uri=media_path))
                    elif media_type == MediaType.VIDEO:
                        videos.append(VideoMedia(uri=media_path))
                    elif media_type == MediaType.SCENE_CLIP:
                        scene_clips.append(self._parse_scene_clip(media_path))
                    else:
                        logger.warning(f"[MEDIA_DETECTOR] Unknown media type for: {media_path}")
                        
                except Exception as e:
                    logger.warning(f"[MEDIA_DETECTOR] Failed to categorize {media_path}: {e}")
                    categorization_errors += 1
                    continue
            
            inventory = MediaInventory(
                images=images,
                videos=videos,
                scene_clips=scene_clips,
                has_images=len(images) > 0,
                has_videos=len(videos) > 0,
                has_scene_clips=len(scene_clips) > 0
            )
            
            logger.info(f"[MEDIA_DETECTOR] Successfully categorized media: {len(images)} images, {len(videos)} videos, {len(scene_clips)} scene clips")
            if categorization_errors > 0:
                logger.warning(f"[MEDIA_DETECTOR] {categorization_errors} files could not be categorized")
            
            return inventory
            
        except Exception as e:
            logger.error(f"[MEDIA_DETECTOR] Critical failure analyzing project media for {project_id}: {e}")
            # Return empty inventory but don't raise exception - let classification flow continue gracefully
            return MediaInventory()
    
    def detect_media_type(self, gcs_path: str) -> MediaType:
        """
        Determine media type from GCS path
        
        Args:
            gcs_path: Google Cloud Storage path
            
        Returns:
            MediaType enum value
        """
        if not gcs_path:
            return MediaType.UNKNOWN
        
        # Check if it's a scene clip based on path structure
        if '/scene_clips/' in gcs_path or '_scene_' in os.path.basename(gcs_path):
            return MediaType.SCENE_CLIP
        
        # Get file extension
        file_extension = Path(gcs_path).suffix.lower()
        
        if file_extension in self.IMAGE_EXTENSIONS:
            return MediaType.IMAGE
        elif file_extension in self.VIDEO_EXTENSIONS:
            return MediaType.VIDEO
        else:
            logger.warning(f"[MEDIA_DETECTOR] Unknown file extension: {file_extension} for {gcs_path}")
            return MediaType.UNKNOWN
    
    def _get_all_project_media_paths(self, user_id: str, project_id: str) -> List[str]:
        """
        Get all media paths for a project from various storage locations
        
        Args:
            user_id: User ID
            project_id: Project ID
            
        Returns:
            List of GCS paths to all media files
        """
        all_paths = []
        
        # Get traditional image repositories
        try:
            logger.debug(f"[MEDIA_DETECTOR] Getting image repositories for project {project_id}")
            image_repos = StorageManager.get_image_repos_for_project(user_id, project_id)
            for repo_path in image_repos:
                try:
                    cloud_path = CloudPath.from_path(repo_path)
                    repo_files = StorageManager.list_blobs_in_path(cloud_path)
                    all_paths.extend(repo_files)
                    logger.debug(f"[MEDIA_DETECTOR] Found {len(repo_files)} files in {repo_path}")
                except Exception as e:
                    logger.warning(f"[MEDIA_DETECTOR] Failed to list files in {repo_path}: {e}")
                    continue
        except Exception as e:
            logger.error(f"[MEDIA_DETECTOR] Failed to get image repositories: {e}")
        
        # Get ALL media from videos folder (videos + scene clips unified)
        try:
            logger.debug(f"[MEDIA_DETECTOR] Getting all media from videos folder for project {project_id}")
            cloud_path = CloudPath(
                bucket_id=settings.GCP.Storage.USER_BUCKET,
                path=Path(f"{user_id}/{project_id}/videos")
            )
            
            video_folder_files = StorageManager.list_blobs_in_path(cloud_path)
            all_paths.extend(video_folder_files)
            logger.debug(f"[MEDIA_DETECTOR] Found {len(video_folder_files)} files in videos folder")
            
        except Exception as e:
            logger.warning(f"[MEDIA_DETECTOR] Failed to get files from videos folder: {e}")
        
        return all_paths
    
    def _parse_scene_clip(self, scene_clip_path: str) -> SceneClipMedia:
        """
        Parse scene clip metadata from file path
        
        Args:
            scene_clip_path: GCS path to scene clip
            
        Returns:
            SceneClipMedia object
        """
        # Extract metadata from filename (assuming format: video_id_scene_001_start_end.mp4)
        filename = os.path.basename(scene_clip_path)
        name_parts = filename.split('_')
        
        try:
            # Try to extract timing information from filename
            if 'scene' in name_parts:
                scene_idx = name_parts.index('scene')
                if len(name_parts) > scene_idx + 3:
                    start_time = float(name_parts[scene_idx + 2])
                    end_time = float(name_parts[scene_idx + 3].split('.')[0])  # Remove extension
                    clip_id = '_'.join(name_parts[:scene_idx + 2])
                    
                    # Reconstruct source video URI (this might need adjustment based on actual storage structure)
                    source_video_uri = scene_clip_path.replace('/scene_clips/', '/videos/').replace(filename, f"{name_parts[0]}.mp4")
                    
                    return SceneClipMedia(
                        uri=scene_clip_path,
                        source_video_uri=source_video_uri,
                        start_time=start_time,
                        end_time=end_time,
                        duration=end_time - start_time,
                        clip_id=clip_id
                    )
        except (ValueError, IndexError) as e:
            logger.warning(f"[MEDIA_DETECTOR] Could not parse scene clip metadata from {filename}: {e}")
        
        # Fallback: create basic scene clip with default values
        return SceneClipMedia(
            uri=scene_clip_path,
            source_video_uri="unknown",
            start_time=0.0,
            end_time=10.0,  # Default 10 second clip
            duration=10.0,
            clip_id=os.path.splitext(filename)[0]
        )
    
    def is_media_type_supported(self, file_path: str) -> bool:
        """
        Check if a file type is supported for processing
        
        Args:
            file_path: Path to file
            
        Returns:
            True if supported, False otherwise
        """
        media_type = self.detect_media_type(file_path)
        return media_type in [MediaType.IMAGE, MediaType.VIDEO, MediaType.SCENE_CLIP]
    
    def get_media_stats(self, inventory: MediaInventory) -> Dict[str, Any]:
        """
        Get statistics about media inventory
        
        Args:
            inventory: MediaInventory object
            
        Returns:
            Dictionary with media statistics
        """
        return {
            "total_files": inventory.total_media_count,
            "image_count": len(inventory.images),
            "video_count": len(inventory.videos),
            "scene_clip_count": len(inventory.scene_clips),
            "is_mixed_media": inventory.is_mixed_media,
            "media_types_present": [
                media_type for media_type, has_media in [
                    ("images", inventory.has_images),
                    ("videos", inventory.has_videos),
                    ("scene_clips", inventory.has_scene_clips)
                ] if has_media
            ]
        }
