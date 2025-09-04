import uuid
import asyncio
from typing import List, Dict, Optional, Any
from datetime import datetime, timezone
import os
import tempfile
from pathlib import Path

from logger import logger
from gcp.storage import StorageManager
from gcp.db import db_client
from config.config import settings
from video.video_actions_model import (
    VideoMetadata, SceneClip, SceneClipTiming, 
    SceneClipClassification, VideoProcessingStatus,
    UploadedVideo
)
from classification.image_classification_manager import ImageClassificationManager
from utils.db_utils import get_session_refs_by_ids


class VideoClipScoring:
    """Enhanced scoring system for video clips with lazy computation"""
    
    @staticmethod
    def calculate_score(scene_metadata: Dict[str, Any], 
                       classification_data: Optional[Dict[str, Any]] = None) -> float:
        """
        Calculate video clip score with lazy loading of expensive computations
        """
        # Basic content score (reuse existing logic)
        content_score = len(scene_metadata.get('detected_features', []))
        
        # Lazy load motion analysis only when needed
        motion_quality = VideoClipScoring._get_motion_quality(scene_metadata)
        duration_fitness = VideoClipScoring._rate_duration_fitness(
            scene_metadata.get('duration', 0)
        )
        
        # Temporal coherence - computed lazily
        temporal_coherence = VideoClipScoring._analyze_temporal_coherence(scene_metadata)
        
        return (content_score * 0.4 + 
                motion_quality * 0.3 + 
                duration_fitness * 0.2 + 
                temporal_coherence * 0.1)
    
    @staticmethod
    def _get_motion_quality(scene_metadata: Dict[str, Any]) -> float:
        """Lazy computation of motion quality"""
        # Return cached value if available
        if 'motion_quality' in scene_metadata:
            return scene_metadata['motion_quality']
        
        # Simple heuristic for now - can be enhanced with actual video analysis
        camera_movement = scene_metadata.get('camera_movement', 'static')
        quality_map = {
            'static': 0.9,
            'smooth_pan': 0.8,
            'smooth_zoom': 0.7,
            'shaky': 0.3
        }
        return quality_map.get(camera_movement, 0.5)
    
    @staticmethod
    def _rate_duration_fitness(duration: float) -> float:
        """Rate how well clip duration fits template needs"""
        # Optimal range: 2-6 seconds
        if 2.0 <= duration <= 6.0:
            return 1.0
        elif 1.0 <= duration < 2.0 or 6.0 < duration <= 8.0:
            return 0.7
        elif duration < 1.0 or duration > 10.0:
            return 0.2
        else:
            return 0.5
    
    @staticmethod
    def _analyze_temporal_coherence(scene_metadata: Dict[str, Any]) -> float:
        """Analyze scene consistency over time - lazy computation"""
        # Return cached if available
        if 'temporal_coherence' in scene_metadata:
            return scene_metadata['temporal_coherence']
        
        # Simple heuristic - can be enhanced with actual analysis
        duration = scene_metadata.get('duration', 0)
        if duration < 1.0:
            return 0.3  # Too short for coherence
        elif duration > 8.0:
            return 0.6  # Might have multiple sub-scenes
        else:
            return 0.8  # Good coherence range


class SceneDetector:
    """Scene detection with lazy processing"""
    
    def __init__(self):
        self.temp_dir = None
    
    async def detect_scenes_metadata(self, video_path: str, 
                                   threshold: float = 0.3) -> List[Dict[str, Any]]:
        """
        Detect scene boundaries and return metadata only (no physical clipping)
        Lazy approach: Only compute timestamps and basic metrics
        """
        try:
            # For now, simulate scene detection
            # In production, use OpenCV/FFmpeg scene detection
            scenes_metadata = await self._simulate_scene_detection(video_path, threshold)
            
            logger.info(f"[SCENE_DETECTOR] Detected {len(scenes_metadata)} scenes in video")
            return scenes_metadata
            
        except Exception as e:
            logger.exception(f"[SCENE_DETECTOR] Failed to detect scenes: {e}")
            raise
    
    async def _simulate_scene_detection(self, video_path: str, 
                                      threshold: float) -> List[Dict[str, Any]]:
        """
        Simulate scene detection for development
        TODO: Replace with actual OpenCV/FFmpeg implementation
        """
        # Simulate video metadata extraction
        video_duration = 120.0  # Mock 2-minute video
        
        # Generate mock scene boundaries
        scenes = []
        current_time = 0.0
        scene_count = 0
        
        while current_time < video_duration and scene_count < 15:  # Max 15 scenes
            # Random scene duration between 3-12 seconds
            import random
            scene_duration = random.uniform(3.0, 12.0)
            end_time = min(current_time + scene_duration, video_duration)
            
            scene_metadata = {
                'scene_id': f"scene_{scene_count:03d}",
                'start_time': current_time,
                'end_time': end_time,
                'duration': end_time - current_time,
                'confidence': random.uniform(0.7, 0.95),
                'change_type': random.choice(['camera_cut', 'content_change', 'lighting_change']),
                'camera_movement': random.choice(['static', 'smooth_pan', 'smooth_zoom', 'shaky']),
                'detected_features': random.sample(
                    ['pool', 'kitchen', 'living_room', 'exterior', 'bathroom', 'bedroom'], 
                    random.randint(1, 4)
                )
            }
            
            scenes.append(scene_metadata)
            current_time = end_time
            scene_count += 1
        
        return scenes
    
    async def extract_scene_clips(self, video_gs_url: str, 
                                scenes_metadata: List[Dict[str, Any]],
                                project_id: str, user_id: str) -> List[SceneClip]:
        """
        Extract physical scene clips based on metadata
        Lazy approach: Only extract clips that pass initial quality filter
        """
        try:
            extracted_clips = []
            
            # Filter scenes by quality before expensive extraction
            filtered_scenes = [
                scene for scene in scenes_metadata 
                if scene['confidence'] > 0.6 and scene['duration'] >= 1.0
            ]
            
            logger.info(f"[SCENE_DETECTOR] Extracting {len(filtered_scenes)}/{len(scenes_metadata)} scenes after quality filter")
            
            for scene_metadata in filtered_scenes:
                # Extract individual clip (mock for now)
                scene_clip = await self._extract_single_clip(
                    video_gs_url, scene_metadata, project_id, user_id
                )
                if scene_clip:
                    extracted_clips.append(scene_clip)
            
            return extracted_clips
            
        except Exception as e:
            logger.exception(f"[SCENE_DETECTOR] Failed to extract scene clips: {e}")
            raise
    
    async def _extract_single_clip(self, video_gs_url: str, 
                                 scene_metadata: Dict[str, Any],
                                 project_id: str, user_id: str) -> Optional[SceneClip]:
        """
        Extract a single scene clip with lazy processing
        """
        try:
            scene_id = scene_metadata['scene_id']
            
            # Mock clip extraction - in production use FFmpeg
            clip_filename = f"{scene_id}.mp4"
            clip_gs_url = f"gs://{settings.GCP.Storage.USER_BUCKET}/{user_id}/{project_id}/scenes/{clip_filename}"
            
            # Simulate clip upload to GCS
            logger.debug(f"[SCENE_DETECTOR] Mock extracting clip {scene_id} to {clip_gs_url}")
            
            # Create SceneClip object with lazy-loaded fields
            scene_clip = SceneClip(
                scene_id=scene_id,
                parent_video_id=scene_metadata.get('parent_video_id', 'unknown'),
                gs_url=clip_gs_url,
                # signed_url and thumbnail_url are lazy-loaded (None initially)
                timing=SceneClipTiming(
                    start_time=scene_metadata['start_time'],
                    end_time=scene_metadata['end_time'],
                    duration=scene_metadata['duration']
                ),
                # classification is lazy-loaded (None initially)
                metadata=VideoMetadata(
                    duration=scene_metadata['duration'],
                    fps=30,
                    resolution=[1920, 1080],
                    aspect_ratio=1.77,
                    orientation="landscape",
                    has_audio=True,
                    file_size_mb=scene_metadata['duration'] * 2.0  # Mock: 2MB per second
                ),
                created_at=datetime.now(timezone.utc)
            )
            
            return scene_clip
            
        except Exception as e:
            logger.exception(f"[SCENE_DETECTOR] Failed to extract clip {scene_metadata.get('scene_id')}: {e}")
            return None


class VideoProcessor:
    """Main video processing orchestrator with lazy computation"""
    
    def __init__(self):
        self.scene_detector = SceneDetector()
        self.classification_manager = ImageClassificationManager()
    
    async def process_uploaded_video(self, video_file_path: str, 
                                   project_id: str, user_id: str,
                                   scene_detection_threshold: float = 0.3,
                                   max_scenes: int = 20) -> Dict[str, Any]:
        """
        Process uploaded video with lazy computation approach
        """
        try:
            video_id = str(uuid.uuid4())
            
            logger.info(f"[VIDEO_PROCESSOR] Starting video processing for project {project_id}")
            
            # Step 1: Scene detection (metadata only - lazy)
            scenes_metadata = await self.scene_detector.detect_scenes_metadata(
                video_file_path, scene_detection_threshold
            )
            
            # Limit scenes if too many detected
            if len(scenes_metadata) > max_scenes:
                # Sort by confidence and take top scenes
                scenes_metadata = sorted(
                    scenes_metadata, 
                    key=lambda x: x['confidence'], 
                    reverse=True
                )[:max_scenes]
            
            # Step 2: Content classification per scene (lazy - only compute scores)
            for scene in scenes_metadata:
                scene['parent_video_id'] = video_id
                # Lazy scoring - only compute basic metrics
                scene['quality_score'] = VideoClipScoring.calculate_score(scene)
            
            # Step 3: Physical clipping (lazy - only extract high-quality scenes)
            scene_clips = await self.scene_detector.extract_scene_clips(
                video_file_path, scenes_metadata, project_id, user_id
            )
            
            # Step 4: Store scene clips in Firestore (lazy - minimal data)
            await self._store_scene_clips_lazy(scene_clips, project_id, user_id)
            
            processing_result = {
                'video_id': video_id,
                'status': 'completed',
                'total_scenes_detected': len(scenes_metadata),
                'scene_clips_extracted': len(scene_clips),
                'scene_clips': scene_clips
            }
            
            logger.info(f"[VIDEO_PROCESSOR] Completed processing video {video_id}")
            return processing_result
            
        except Exception as e:
            logger.exception(f"[VIDEO_PROCESSOR] Failed to process video: {e}")
            raise
    
    async def _store_scene_clips_lazy(self, scene_clips: List[SceneClip], 
                                    project_id: str, user_id: str):
        """
        Store scene clips with lazy approach - minimal initial data
        """
        try:
            _, project_ref, _ = get_session_refs_by_ids(
                user_id=user_id, 
                project_id=project_id
            )
            
            # Get existing project data
            project_doc = project_ref.get()
            if not project_doc.exists:
                logger.error(f"[VIDEO_PROCESSOR] Project {project_id} not found")
                return
            
            project_data = project_doc.to_dict()
            
            # Initialize media structure if needed
            if 'media' not in project_data:
                project_data['media'] = {}
            if 'scene_clips' not in project_data['media']:
                project_data['media']['scene_clips'] = []
            
            # Add scene clips with lazy-loaded fields as None
            for clip in scene_clips:
                clip_data = {
                    'scene_id': clip.scene_id,
                    'parent_video_id': clip.parent_video_id,
                    'gs_url': clip.gs_url,
                    'timing': clip.timing.model_dump(),
                    'metadata': clip.metadata.model_dump(),
                    'usage': clip.usage.model_dump(),
                    'created_at': clip.created_at,
                    # Lazy-loaded fields stored as None initially
                    'signed_url': None,
                    'thumbnail_url': None,
                    'classification': None
                }
                project_data['media']['scene_clips'].append(clip_data)
            
            # Update project with new scene clips
            project_ref.update({
                'media': project_data['media'],
                'stats.total_scene_clips': len(project_data['media']['scene_clips']),
                'stats.last_media_update': datetime.now(timezone.utc)
            })
            
            logger.info(f"[VIDEO_PROCESSOR] Stored {len(scene_clips)} scene clips lazily")
            
        except Exception as e:
            logger.exception(f"[VIDEO_PROCESSOR] Failed to store scene clips: {e}")
            raise


# Lazy loading utilities
class LazyVideoLoader:
    """Utility class for lazy loading video-related data"""
    
    @staticmethod
    async def load_signed_urls(scene_clips: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Lazy load signed URLs for scene clips"""
        for clip in scene_clips:
            if not clip.get('signed_url') and clip.get('gs_url'):
                clip['signed_url'] = StorageManager.generate_signed_url_from_gs_url(
                    clip['gs_url']
                )
        return scene_clips
    
    @staticmethod
    async def load_classifications(scene_clips: List[Dict[str, Any]], 
                                 classification_manager: ImageClassificationManager) -> List[Dict[str, Any]]:
        """Lazy load classifications for scene clips"""
        for clip in scene_clips:
            if not clip.get('classification'):
                # Simulate classification - in production, analyze the actual clip
                clip['classification'] = {
                    'content_type': 'exterior',  # Mock
                    'quality_score': clip.get('quality_score', 0.5),
                    'visual_features': ['generic'],
                    'lighting_quality': 'good',
                    'camera_movement': clip.get('camera_movement', 'static'),
                    'composition_score': 0.7,
                    'motion_quality': 0.8,
                    'duration_fitness': VideoClipScoring._rate_duration_fitness(
                        clip.get('timing', {}).get('duration', 0)
                    ),
                    'temporal_coherence': 0.8
                }
        return scene_clips
