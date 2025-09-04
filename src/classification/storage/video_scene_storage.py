"""
Video Scene Storage Manager
Handles storage and retrieval of enhanced video scene classifications following image classification pattern.
Stores data at projects/{project_id} with key 'video_scenes_classification' for consistency.
"""

from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

from logger import logger
from utils.session_utils import get_session_refs_by_ids
from config.config import settings


class VideoScenesStorage:
    """
    Manages storage and retrieval of enhanced video scene classifications.
    Follows the same pattern as image classification for architectural consistency.
    """
    
    # Storage key in project document (following image_classification pattern)
    VIDEO_SCENES_CLASSIFICATION_KEY = "video_scenes_classification"
    
    @classmethod
    def store_video_scenes(cls, user_id: str, project_id: str, video_uri: str, 
                          video_scenes_data: Dict[str, Any]) -> bool:
        """
        Store enhanced video scene classification data in Firestore.
        
        Storage Pattern (following image classification):
        projects/{project_id} -> {
            "video_scenes_classification": {
                "videos": {
                    "video_filename.MOV": {
                        "video_uri": "gs://...",
                        "video_duration": 36.4,
                        "total_scenes": 12,
                        "scenes": [...],
                        "processing_metadata": {...},
                        "processed_at": "2025-09-03T20:30:00Z"
                    }
                }
            }
        }
        
        Args:
            user_id: User ID
            project_id: Project ID  
            video_uri: GCS URI of the video
            video_scenes_data: Complete video scene classification data
            
        Returns:
            bool: True if storage successful, False otherwise
        """
        try:
            # Get project reference
            _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            
            # Extract video filename for key
            video_filename = Path(video_uri).name
            
            # Get existing data or initialize
            project_doc = project_ref.get()
            project_data = project_doc.to_dict() if project_doc.exists else {}
            
            # Initialize video scenes classification structure if needed
            if cls.VIDEO_SCENES_CLASSIFICATION_KEY not in project_data:
                project_data[cls.VIDEO_SCENES_CLASSIFICATION_KEY] = {"videos": {}}
            elif "videos" not in project_data[cls.VIDEO_SCENES_CLASSIFICATION_KEY]:
                project_data[cls.VIDEO_SCENES_CLASSIFICATION_KEY]["videos"] = {}
            
            # Store video scene data
            project_data[cls.VIDEO_SCENES_CLASSIFICATION_KEY]["videos"][video_filename] = video_scenes_data
            
            # Update project document
            project_ref.set({cls.VIDEO_SCENES_CLASSIFICATION_KEY: project_data[cls.VIDEO_SCENES_CLASSIFICATION_KEY]}, merge=True)
            
            logger.info(f"[VIDEO_SCENES_STORAGE] Stored scene classification for {video_filename} with {video_scenes_data.get('total_scenes', 0)} scenes")
            return True
            
        except Exception as e:
            logger.error(f"[VIDEO_SCENES_STORAGE] Failed to store video scene classification: {e}")
            return False
    
    @classmethod
    def fetch_video_scenes(cls, user_id: str, project_id: str, video_uri: str) -> Optional[Dict[str, Any]]:
        """
        Fetch enhanced video scene classification data from Firestore.
        
        Args:
            user_id: User ID
            project_id: Project ID
            video_uri: GCS URI of the video (used to extract filename)
            
        Returns:
            Dict with video scene data or None if not found
        """
        try:
            # Get project reference
            _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            
            # Extract video filename for key
            video_filename = Path(video_uri).name
            
            # Get project document
            project_doc = project_ref.get()
            if not project_doc.exists:
                logger.warning(f"[VIDEO_SCENES_STORAGE] Project {project_id} not found")
                return None
            
            project_data = project_doc.to_dict()
            
            # Check if video scenes classification exists
            if cls.VIDEO_SCENES_CLASSIFICATION_KEY not in project_data:
                logger.warning(f"[VIDEO_SCENES_STORAGE] No video scenes classification found in project {project_id}")
                return None
            
            videos_data = project_data[cls.VIDEO_SCENES_CLASSIFICATION_KEY].get("videos", {})
            
            # Check if specific video exists
            if video_filename not in videos_data:
                logger.warning(f"[VIDEO_SCENES_STORAGE] No scene classification found for video {video_filename}")
                return None
            
            video_scenes_data = videos_data[video_filename]
            logger.info(f"[VIDEO_SCENES_STORAGE] Retrieved scene classification for {video_filename} with {video_scenes_data.get('total_scenes', 0)} scenes")
            
            return video_scenes_data
            
        except Exception as e:
            logger.error(f"[VIDEO_SCENES_STORAGE] Failed to fetch video scene classification: {e}")
            return None
    
    @classmethod
    def list_classified_videos(cls, user_id: str, project_id: str) -> List[str]:
        """
        List all videos that have scene classifications in this project.
        
        Args:
            user_id: User ID
            project_id: Project ID
            
        Returns:
            List of video filenames that have classifications
        """
        try:
            # Get project reference
            _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            
            # Get project document
            project_doc = project_ref.get()
            if not project_doc.exists:
                return []
            
            project_data = project_doc.to_dict()
            
            # Check if video scenes classification exists
            if cls.VIDEO_SCENES_CLASSIFICATION_KEY not in project_data:
                return []
            
            videos_data = project_data[cls.VIDEO_SCENES_CLASSIFICATION_KEY].get("videos", {})
            return list(videos_data.keys())
            
        except Exception as e:
            logger.error(f"[VIDEO_SCENES_STORAGE] Failed to list classified videos: {e}")
            return []
    
    @classmethod
    def delete_video_scenes(cls, user_id: str, project_id: str, video_uri: str) -> bool:
        """
        Delete video scene classification data for a specific video.
        
        Args:
            user_id: User ID
            project_id: Project ID
            video_uri: GCS URI of the video to delete
            
        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            # Get project reference
            _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            
            # Extract video filename for key
            video_filename = Path(video_uri).name
            
            # Get existing data
            project_doc = project_ref.get()
            if not project_doc.exists:
                logger.warning(f"[VIDEO_SCENES_STORAGE] Project {project_id} not found")
                return False
            
            project_data = project_doc.to_dict()
            
            # Check if video scenes classification exists
            if cls.VIDEO_SCENES_CLASSIFICATION_KEY not in project_data:
                logger.warning(f"[VIDEO_SCENES_STORAGE] No video scenes classification found in project {project_id}")
                return False
            
            videos_data = project_data[cls.VIDEO_SCENES_CLASSIFICATION_KEY].get("videos", {})
            
            # Check if specific video exists
            if video_filename not in videos_data:
                logger.warning(f"[VIDEO_SCENES_STORAGE] No scene classification found for video {video_filename}")
                return False
            
            # Remove video from data
            del videos_data[video_filename]
            
            # Update project document
            project_ref.set({cls.VIDEO_SCENES_CLASSIFICATION_KEY: {"videos": videos_data}}, merge=True)
            
            logger.info(f"[VIDEO_SCENES_STORAGE] Deleted scene classification for {video_filename}")
            return True
            
        except Exception as e:
            logger.error(f"[VIDEO_SCENES_STORAGE] Failed to delete video scene classification: {e}")
            return False
    
    @classmethod
    def get_project_video_stats(cls, user_id: str, project_id: str) -> Dict[str, Any]:
        """
        Get summary statistics for all video scene classifications in a project.
        
        Args:
            user_id: User ID
            project_id: Project ID
            
        Returns:
            Dict with project video classification statistics
        """
        try:
            # Get project reference
            _, project_ref, _ = get_session_refs_by_ids(user_id=user_id, project_id=project_id)
            
            # Get project document
            project_doc = project_ref.get()
            if not project_doc.exists:
                return {"total_videos": 0, "total_scenes": 0, "videos": []}
            
            project_data = project_doc.to_dict()
            
            # Check if video scenes classification exists
            if cls.VIDEO_SCENES_CLASSIFICATION_KEY not in project_data:
                return {"total_videos": 0, "total_scenes": 0, "videos": []}
            
            videos_data = project_data[cls.VIDEO_SCENES_CLASSIFICATION_KEY].get("videos", {})
            
            # Calculate statistics
            total_videos = len(videos_data)
            total_scenes = sum(video_data.get("total_scenes", 0) for video_data in videos_data.values())
            
            # Video summaries
            video_summaries = []
            for video_filename, video_data in videos_data.items():
                video_summaries.append({
                    "filename": video_filename,
                    "total_scenes": video_data.get("total_scenes", 0),
                    "duration": video_data.get("video_duration", 0.0),
                    "processed_at": video_data.get("processed_at")
                })
            
            return {
                "total_videos": total_videos,
                "total_scenes": total_scenes,
                "videos": video_summaries
            }
            
        except Exception as e:
            logger.error(f"[VIDEO_SCENES_STORAGE] Failed to get project video stats: {e}")
            return {"total_videos": 0, "total_scenes": 0, "videos": []}
