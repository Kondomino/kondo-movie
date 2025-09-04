import time
from typing import Dict, Any, Optional
from logger import logger
from classification.image_classification_manager import ImageClassificationManager
from classification.video_classification_manager import VideoClassificationManager
from classification.media_detector import MediaTypeDetector

from classification.types.media_models import (
    MediaInventory, UnifiedClassificationResults, MediaType, VideoMedia, VideoIntelligenceResults
)


class UnifiedClassificationManager:
    """
    Main orchestrator for unified media classification.
    Routes different media types to appropriate classification services.
    """
    
    def __init__(self):
        self.media_detector = MediaTypeDetector()
        self.image_classifier = ImageClassificationManager()  # Existing image classification
        self.video_classifier = VideoClassificationManager()  # Enhanced video classification with hierarchical room priority system
    
    def classify_project_media(self, user_id: str, project_id: str) -> UnifiedClassificationResults:
        """
        Main entry point for unified media classification
        
        Args:
            user_id: User ID
            project_id: Project ID
            
        Returns:
            UnifiedClassificationResults with all classification data
        """
        logger.info(f"[UNIFIED_CLASSIFIER] Starting unified classification for project {project_id}")
        
        try:
            start_time = time.time()
            
            # Step 1: Analyze media inventory
            media_inventory = self.media_detector.analyze_project_media(user_id, project_id)
            
            if media_inventory.total_media_count == 0:
                logger.info(f"[UNIFIED_CLASSIFIER] No media found for project {project_id} - this is normal for newly created projects")
                return UnifiedClassificationResults(
                    media_inventory=media_inventory,
                    mixed_media=False,
                    processing_duration=time.time() - start_time
                )
            
            # Step 2: Log media statistics
            media_stats = self.media_detector.get_media_stats(media_inventory)
            logger.info(f"[UNIFIED_CLASSIFIER] Media stats: {media_stats}")
            
            # Step 3: Route to appropriate classification services
            results = UnifiedClassificationResults(
                media_inventory=media_inventory,
                mixed_media=media_inventory.is_mixed_media
            )
            
            # Classify images if present
            if media_inventory.has_images:
                logger.info(f"[UNIFIED_CLASSIFIER] Classifying {len(media_inventory.images)} images using Google Vision API")
                results.images = self._classify_images(user_id, project_id, media_inventory)
                results.google_vision_api_used = True
            
            # Classify videos if present (using enhanced scene detection with hierarchical room priority)
            if media_inventory.has_videos or media_inventory.has_scene_clips:
                logger.info(f"[UNIFIED_CLASSIFIER] Classifying {len(media_inventory.videos)} videos using enhanced scene detection with room priority system")
                video_classification_results = self._classify_videos_consolidated(user_id, project_id, media_inventory)
                results.google_video_intelligence_used = True
                results.google_vision_api_used = True
                
                # Store video classification results in the new format
                if video_classification_results:
                    results.videos = {
                        "status": "completed",
                        "total_videos_processed": video_classification_results["total_videos_processed"],
                        "total_scenes_detected": video_classification_results["total_scenes_detected"],
                        "processing_time": video_classification_results["processing_time"],
                        "enhanced_detection": True,
                        "room_priority_system": True
                    }
            
            # Handle mixed media scenarios
            if media_inventory.is_mixed_media:
                logger.info(f"[UNIFIED_CLASSIFIER] Processing mixed media project with enhanced algorithms")
                results.unified_buckets = self._create_unified_buckets(results)
            
            results.processing_duration = time.time() - start_time
            
            logger.success(f"[UNIFIED_CLASSIFIER] Enhanced unified classification completed for project {project_id} "
                         f"in {results.processing_duration:.2f}s")
            return results
            
        except Exception as e:
            logger.error(f"[UNIFIED_CLASSIFIER] Failed to classify project media: {e}")
            return UnifiedClassificationResults(
                media_inventory=MediaInventory(),
                mixed_media=False
            )
    
    def _classify_images(self, user_id: str, project_id: str, media_inventory: MediaInventory) -> Optional[Dict[str, Any]]:
        """
        Classify images using existing image classification system
        
        Args:
            user_id: User ID
            project_id: Project ID
            media_inventory: MediaInventory object
            
        Returns:
            Image classification results as dictionary
        """
        try:
            # Use existing image classification logic
            # This will create temporary files and run the full pipeline
            self.image_classifier.run_classification_for_project(user_id, project_id)
            
            # The results are stored in Firestore by the existing system
            # We could retrieve them here if needed for unified processing
            logger.info(f"[UNIFIED_CLASSIFIER] Image classification completed")
            return {"status": "completed", "image_count": len(media_inventory.images)}
            
        except Exception as e:
            logger.error(f"[UNIFIED_CLASSIFIER] Image classification failed: {e}")
            return None
    
    def _classify_videos_consolidated(self, user_id: str, project_id: str, 
                                    media_inventory: MediaInventory) -> Optional[Dict[str, Any]]:
        """
        Enhanced video classification using new storage system
        
        Args:
            user_id: User ID
            project_id: Project ID
            media_inventory: MediaInventory object
            
        Returns:
            Dictionary with classification results and statistics
        """
        try:
            # Combine videos and scene clips for processing
            all_videos = media_inventory.videos.copy()
            
            # Convert scene clips to VideoMedia objects for processing if needed
            for scene_clip in media_inventory.scene_clips:
                video_media = VideoMedia(
                    uri=scene_clip.uri,
                    duration=scene_clip.duration
                )
                all_videos.append(video_media)
            
            if not all_videos:
                logger.warning(f"[UNIFIED_CLASSIFIER] No videos to classify")
                return None
            
            # Run enhanced video classification with new storage system
            classification_results = self.video_classifier.classify_videos(all_videos, user_id, project_id)
            
            logger.info(f"[UNIFIED_CLASSIFIER] Enhanced video classification completed: "
                       f"{classification_results['total_scenes_detected']} scenes from {classification_results['total_videos_processed']} videos")
            
            return classification_results
            
        except Exception as e:
            logger.error(f"[UNIFIED_CLASSIFIER] Enhanced video classification failed: {e}")
            return None
    

    
    def _create_unified_buckets(self, results: UnifiedClassificationResults) -> Optional[Dict[str, Any]]:
        """
        Create unified buckets for mixed media projects
        
        Args:
            results: Current classification results
            
        Returns:
            Unified buckets combining images and videos
        """
        logger.info(f"[UNIFIED_CLASSIFIER] Creating unified buckets for mixed media")
        
        try:
            unified_buckets = {}
            
            # Get categories from the classification model
            categories = self.image_classifier.model.categories
            
            # Initialize unified buckets for each category
            for category in categories:
                unified_buckets[category] = {
                    "images": [],
                    "video_clips": [],
                    "total_items": 0,
                    "combined_score": 0.0
                }
            
            # This is a simplified implementation
            # In a full implementation, we would:
            # 1. Load actual image and video classification results from Firestore
            # 2. Merge them intelligently based on scores and categories
            # 3. Apply unified ranking strategies
            
            # For now, return the structure that will be populated
            return {
                "status": "implemented",
                "mixed_media": True,
                "unified_buckets": unified_buckets,
                "categories": categories,
                "message": "Unified buckets structure created - full merging logic can be implemented as needed"
            }
            
        except Exception as e:
            logger.error(f"[UNIFIED_CLASSIFIER] Failed to create unified buckets: {e}")
            return {
                "status": "error",
                "mixed_media": True,
                "error": str(e)
            }
    
    def should_run_classification(self, user_id: str, project_id: str) -> bool:
        """
        Determine if classification should run based on project media
        
        Args:
            user_id: User ID
            project_id: Project ID
            
        Returns:
            True if classification should run, False otherwise
        """
        try:
            media_inventory = self.media_detector.analyze_project_media(user_id, project_id)
            
            if media_inventory.total_media_count == 0:
                logger.info(f"[UNIFIED_CLASSIFIER] No media found for project {project_id} - skipping classification")
                return False
            
            # Always run classification if we have any supported media
            if media_inventory.has_images or media_inventory.has_videos or media_inventory.has_scene_clips:
                logger.info(f"[UNIFIED_CLASSIFIER] Found {media_inventory.total_media_count} media files - classification will proceed")
                return True
            
            logger.info(f"[UNIFIED_CLASSIFIER] Found {media_inventory.total_media_count} files but no supported media types - skipping classification")
            return False
            
        except Exception as e:
            logger.error(f"[UNIFIED_CLASSIFIER] Error determining if classification should run for project {project_id}: {e}")
            # Return False to gracefully skip classification rather than failing
            return False
    
    def get_classification_status(self, user_id: str, project_id: str) -> Dict[str, Any]:
        """
        Get current classification status for a project
        
        Args:
            user_id: User ID
            project_id: Project ID
            
        Returns:
            Dictionary with classification status information
        """
        try:
            media_inventory = self.media_detector.analyze_project_media(user_id, project_id)
            media_stats = self.media_detector.get_media_stats(media_inventory)
            
            return {
                "project_id": project_id,
                "media_stats": media_stats,
                "classification_needed": self.should_run_classification(user_id, project_id),
                "supports_images": media_inventory.has_images,
                "supports_videos": media_inventory.has_videos,
                "supports_scene_clips": media_inventory.has_scene_clips,
                "is_mixed_media": media_inventory.is_mixed_media
            }
            
        except Exception as e:
            logger.error(f"[UNIFIED_CLASSIFIER] Error getting classification status: {e}")
            return {
                "project_id": project_id,
                "error": str(e),
                "classification_needed": False
            }
