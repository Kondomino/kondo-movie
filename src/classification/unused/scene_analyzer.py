import os
import cv2
import numpy as np
from typing import List, Tuple, Optional
from tempfile import NamedTemporaryFile
import uuid

from logger import logger
from gcp.storage import StorageManager
from classification.types.media_models import SceneClip


class SceneAnalyzer:
    """
    Analyzes videos to detect and extract meaningful scene clips.
    Uses computer vision techniques for scene detection and quality assessment.
    """
    
    def __init__(self):
        # Scene detection parameters
        self.min_scene_duration = 1.5  # Minimum scene length in seconds
        self.max_scene_duration = 12.0  # Maximum scene length in seconds
        self.scene_threshold = 30.0  # Threshold for scene change detection
        self.quality_threshold = 0.3  # Minimum quality score to keep a scene
        
    def extract_scene_clips(self, video_uri: str, user_id: str, project_id: str) -> List[SceneClip]:
        """
        Extract meaningful scene clips from a video
        
        Args:
            video_uri: GCS URI of the video
            user_id: User ID for context
            project_id: Project ID for context
            
        Returns:
            List of SceneClip objects
        """
        logger.info(f"[SCENE_ANALYZER] Extracting scenes from video: {video_uri}")
        
        try:
            # Download video temporarily for analysis
            with NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_video_path = temp_file.name
                
            # Download video from GCS
            StorageManager.download_blob_to_file(video_uri, temp_video_path)
            
            try:
                # Extract scenes from the temporary video file
                scenes = self._detect_scenes(temp_video_path)
                
                # Filter scenes by quality and duration
                quality_scenes = self._filter_quality_scenes(scenes, temp_video_path)
                
                # Create SceneClip objects
                scene_clips = []
                video_id = self._extract_video_id(video_uri)
                
                for i, scene in enumerate(quality_scenes):
                    clip = SceneClip(
                        clip_id=f"{video_id}_scene_{i:03d}",
                        source_video_uri=video_uri,
                        start_time=scene['start_time'],
                        end_time=scene['end_time'],
                        motion_intensity=scene.get('motion_intensity', 0.5),
                        audio_level=scene.get('audio_level', 0.5),
                        brightness=scene.get('brightness', 0.5),
                        stability=scene.get('stability', 0.5)
                    )
                    scene_clips.append(clip)
                
                logger.info(f"[SCENE_ANALYZER] Extracted {len(scene_clips)} quality scene clips")
                return scene_clips
                
            finally:
                # Clean up temporary file
                if os.path.exists(temp_video_path):
                    os.unlink(temp_video_path)
                    
        except Exception as e:
            logger.error(f"[SCENE_ANALYZER] Failed to extract scenes from {video_uri}: {e}")
            return []
    
    def _detect_scenes(self, video_path: str) -> List[dict]:
        """
        Detect scene boundaries in video using frame difference analysis
        
        Args:
            video_path: Path to video file
            
        Returns:
            List of scene dictionaries with start/end times
        """
        logger.debug(f"[SCENE_ANALYZER] Detecting scenes in video: {video_path}")
        
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Could not open video file: {video_path}")
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30.0  # Default fallback
            
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = frame_count / fps
            
            logger.debug(f"[SCENE_ANALYZER] Video stats: {frame_count} frames, {fps} fps, {duration:.2f}s duration")
            
            scenes = []
            prev_frame = None
            scene_start = 0.0
            frame_idx = 0
            
            # Sample frames for scene detection (every 0.5 seconds)
            frame_skip = max(1, int(fps * 0.5))
            
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                current_time = frame_idx / fps
                
                # Only process every nth frame for efficiency
                if frame_idx % frame_skip == 0:
                    # Convert to grayscale for comparison
                    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    
                    if prev_frame is not None:
                        # Calculate frame difference
                        diff = cv2.absdiff(prev_frame, gray_frame)
                        diff_score = np.mean(diff)
                        
                        # Detect scene change
                        if diff_score > self.scene_threshold:
                            # End current scene
                            scene_duration = current_time - scene_start
                            if scene_duration >= self.min_scene_duration:
                                scenes.append({
                                    'start_time': scene_start,
                                    'end_time': current_time,
                                    'duration': scene_duration
                                })
                            
                            # Start new scene
                            scene_start = current_time
                    
                    prev_frame = gray_frame.copy()
                
                frame_idx += 1
            
            # Add final scene
            final_duration = duration - scene_start
            if final_duration >= self.min_scene_duration:
                scenes.append({
                    'start_time': scene_start,
                    'end_time': duration,
                    'duration': final_duration
                })
            
            cap.release()
            
            logger.debug(f"[SCENE_ANALYZER] Detected {len(scenes)} raw scenes")
            return scenes
            
        except Exception as e:
            logger.error(f"[SCENE_ANALYZER] Scene detection failed: {e}")
            return []
    
    def _filter_quality_scenes(self, scenes: List[dict], video_path: str) -> List[dict]:
        """
        Filter scenes based on quality metrics
        
        Args:
            scenes: List of raw scene dictionaries
            video_path: Path to video file
            
        Returns:
            List of filtered, high-quality scenes
        """
        logger.debug(f"[SCENE_ANALYZER] Filtering {len(scenes)} scenes for quality")
        
        quality_scenes = []
        
        try:
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30.0
            
            for scene in scenes:
                # Skip scenes that are too short or too long
                duration = scene['duration']
                if duration < self.min_scene_duration or duration > self.max_scene_duration:
                    continue
                
                # Analyze scene quality
                quality_metrics = self._analyze_scene_quality(
                    cap, scene['start_time'], scene['end_time'], fps
                )
                
                # Calculate overall quality score
                quality_score = self._calculate_scene_quality_score(quality_metrics)
                
                if quality_score >= self.quality_threshold:
                    # Add quality metrics to scene
                    scene.update(quality_metrics)
                    scene['quality_score'] = quality_score
                    quality_scenes.append(scene)
            
            cap.release()
            
            # Sort by quality score (best first)
            quality_scenes.sort(key=lambda s: s['quality_score'], reverse=True)
            
            # Limit to top scenes to avoid overwhelming the system
            max_scenes = 20
            if len(quality_scenes) > max_scenes:
                quality_scenes = quality_scenes[:max_scenes]
                logger.info(f"[SCENE_ANALYZER] Limited to top {max_scenes} quality scenes")
            
            logger.info(f"[SCENE_ANALYZER] Filtered to {len(quality_scenes)} quality scenes")
            return quality_scenes
            
        except Exception as e:
            logger.error(f"[SCENE_ANALYZER] Quality filtering failed: {e}")
            return scenes  # Return unfiltered scenes as fallback
    
    def _analyze_scene_quality(self, cap: cv2.VideoCapture, start_time: float, 
                              end_time: float, fps: float) -> dict:
        """
        Analyze quality metrics for a specific scene
        
        Args:
            cap: OpenCV VideoCapture object
            start_time: Scene start time in seconds
            end_time: Scene end time in seconds
            fps: Frames per second
            
        Returns:
            Dictionary with quality metrics
        """
        try:
            # Sample a few frames from the scene
            sample_times = [
                start_time + (end_time - start_time) * 0.2,  # 20%
                start_time + (end_time - start_time) * 0.5,  # 50%
                start_time + (end_time - start_time) * 0.8   # 80%
            ]
            
            brightness_scores = []
            motion_scores = []
            stability_scores = []
            prev_sample = None
            
            for sample_time in sample_times:
                frame_number = int(sample_time * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
                
                ret, frame = cap.read()
                if not ret:
                    continue
                
                # Brightness analysis
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                brightness = np.mean(gray) / 255.0
                brightness_scores.append(brightness)
                
                # Motion and stability analysis
                if prev_sample is not None:
                    # Calculate optical flow for motion
                    flow = cv2.calcOpticalFlowPyrLK(
                        prev_sample, gray, None, None
                    )[0] if prev_sample is not None else None
                    
                    if flow is not None and len(flow) > 0:
                        motion = np.mean(np.linalg.norm(flow, axis=2))
                        motion_scores.append(min(motion / 10.0, 1.0))  # Normalize
                        
                        # Stability is inverse of motion variance
                        stability = 1.0 - min(np.var(flow) / 100.0, 1.0)
                        stability_scores.append(max(stability, 0.0))
                
                prev_sample = gray.copy()
            
            # Calculate averages
            return {
                'brightness': np.mean(brightness_scores) if brightness_scores else 0.5,
                'motion_intensity': np.mean(motion_scores) if motion_scores else 0.5,
                'stability': np.mean(stability_scores) if stability_scores else 0.5,
                'audio_level': 0.5  # Placeholder - would need audio analysis
            }
            
        except Exception as e:
            logger.warning(f"[SCENE_ANALYZER] Quality analysis failed: {e}")
            return {
                'brightness': 0.5,
                'motion_intensity': 0.5,
                'stability': 0.5,
                'audio_level': 0.5
            }
    
    def _calculate_scene_quality_score(self, metrics: dict) -> float:
        """
        Calculate overall quality score from metrics
        
        Args:
            metrics: Dictionary of quality metrics
            
        Returns:
            Quality score between 0.0 and 1.0
        """
        scores = []
        
        # Brightness score (prefer well-lit scenes, avoid too dark/bright)
        brightness = metrics.get('brightness', 0.5)
        brightness_score = 1.0 - abs(0.6 - brightness)  # Optimal around 0.6
        scores.append(brightness_score)
        
        # Motion score (prefer moderate motion)
        motion = metrics.get('motion_intensity', 0.5)
        motion_score = 1.0 - abs(0.4 - motion)  # Optimal around 0.4
        scores.append(motion_score)
        
        # Stability score (prefer stable scenes)
        stability = metrics.get('stability', 0.5)
        scores.append(stability)
        
        # Return weighted average
        return sum(scores) / len(scores)
    
    def _extract_video_id(self, video_uri: str) -> str:
        """
        Extract a video ID from the GCS URI
        
        Args:
            video_uri: GCS URI of the video
            
        Returns:
            Video ID string
        """
        try:
            # Extract filename without extension
            filename = os.path.basename(video_uri)
            video_id = os.path.splitext(filename)[0]
            
            # Clean up the ID (remove special characters)
            video_id = ''.join(c for c in video_id if c.isalnum() or c in '-_')
            
            return video_id or str(uuid.uuid4())[:8]
            
        except Exception:
            return str(uuid.uuid4())[:8]
