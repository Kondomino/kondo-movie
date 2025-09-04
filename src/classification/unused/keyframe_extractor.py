import os
import cv2
import uuid
from typing import List, Optional
from tempfile import NamedTemporaryFile
import numpy as np

from logger import logger
from gcp.storage import StorageManager
from classification.types.media_models import Keyframe


class KeyframeExtractor:
    """
    Extracts representative keyframes from video scene clips.
    Uploads keyframes to GCS for later classification.
    """
    
    def __init__(self):
        self.keyframe_quality = 95  # JPEG quality for keyframes
        self.target_resolution = (1280, 720)  # Target resolution for keyframes
    
    def extract_keyframes(self, video_uri: str, start_time: float, end_time: float,
                         user_id: str, project_id: str, clip_id: str,
                         num_keyframes: int = 3) -> List[Keyframe]:
        """
        Extract representative keyframes from a video scene clip
        
        Args:
            video_uri: GCS URI of the source video
            start_time: Start time of the clip in seconds
            end_time: End time of the clip in seconds
            user_id: User ID for storage context
            project_id: Project ID for storage context
            clip_id: Unique clip identifier
            num_keyframes: Number of keyframes to extract (default: 3)
            
        Returns:
            List of Keyframe objects with GCS URIs
        """
        logger.debug(f"[KEYFRAME_EXTRACTOR] Extracting {num_keyframes} keyframes from clip {clip_id}")
        
        try:
            # Download video temporarily for keyframe extraction
            with NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_video_path = temp_file.name
            
            # Download video from GCS
            StorageManager.download_blob_to_file(video_uri, temp_video_path)
            
            try:
                # Extract keyframes from the temporary video
                keyframes = self._extract_keyframes_from_video(
                    temp_video_path, start_time, end_time, 
                    user_id, project_id, clip_id, num_keyframes
                )
                
                logger.debug(f"[KEYFRAME_EXTRACTOR] Successfully extracted {len(keyframes)} keyframes")
                return keyframes
                
            finally:
                # Clean up temporary video file
                if os.path.exists(temp_video_path):
                    os.unlink(temp_video_path)
                    
        except Exception as e:
            logger.error(f"[KEYFRAME_EXTRACTOR] Failed to extract keyframes for clip {clip_id}: {e}")
            return []
    
    def _extract_keyframes_from_video(self, video_path: str, start_time: float, end_time: float,
                                    user_id: str, project_id: str, clip_id: str,
                                    num_keyframes: int) -> List[Keyframe]:
        """
        Extract keyframes from video file and upload to GCS
        
        Args:
            video_path: Local path to video file
            start_time: Clip start time in seconds
            end_time: Clip end time in seconds
            user_id: User ID
            project_id: Project ID
            clip_id: Clip identifier
            num_keyframes: Number of keyframes to extract
            
        Returns:
            List of Keyframe objects
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Could not open video file: {video_path}")
            
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps <= 0:
                fps = 30.0  # Default fallback
            
            duration = end_time - start_time
            
            # Calculate keyframe timestamps
            keyframe_timestamps = self._calculate_keyframe_timestamps(
                start_time, end_time, num_keyframes
            )
            
            keyframes = []
            
            for i, timestamp in enumerate(keyframe_timestamps):
                try:
                    # Extract frame at timestamp
                    frame = self._extract_frame_at_timestamp(cap, timestamp, fps)
                    if frame is None:
                        continue
                    
                    # Process and optimize frame
                    processed_frame = self._process_frame(frame)
                    
                    # Upload frame to GCS
                    keyframe_uri = self._upload_keyframe_to_gcs(
                        processed_frame, user_id, project_id, clip_id, i
                    )
                    
                    if keyframe_uri:
                        keyframe = Keyframe(
                            uri=keyframe_uri,
                            timestamp=timestamp,
                            position=i,
                            is_hero_candidate=True
                        )
                        keyframes.append(keyframe)
                        
                except Exception as e:
                    logger.warning(f"[KEYFRAME_EXTRACTOR] Failed to extract keyframe {i} at {timestamp}s: {e}")
                    continue
            
            cap.release()
            return keyframes
            
        except Exception as e:
            logger.error(f"[KEYFRAME_EXTRACTOR] Keyframe extraction failed: {e}")
            return []
    
    def _calculate_keyframe_timestamps(self, start_time: float, end_time: float, 
                                     num_keyframes: int) -> List[float]:
        """
        Calculate optimal timestamps for keyframe extraction
        
        Args:
            start_time: Clip start time
            end_time: Clip end time
            num_keyframes: Number of keyframes to extract
            
        Returns:
            List of timestamps in seconds
        """
        duration = end_time - start_time
        
        if num_keyframes == 1:
            # Single keyframe: middle of the clip
            return [start_time + duration * 0.5]
        
        elif num_keyframes == 2:
            # Two keyframes: 25% and 75%
            return [
                start_time + duration * 0.25,
                start_time + duration * 0.75
            ]
        
        elif num_keyframes == 3:
            # Three keyframes: avoid fade-in/out at edges
            return [
                start_time + duration * 0.15,  # Near beginning
                start_time + duration * 0.5,   # Middle
                start_time + duration * 0.85   # Near end
            ]
        
        else:
            # More keyframes: distribute evenly with edge padding
            padding = 0.1  # 10% padding from edges
            usable_duration = duration * (1 - 2 * padding)
            
            timestamps = []
            for i in range(num_keyframes):
                ratio = i / (num_keyframes - 1) if num_keyframes > 1 else 0.5
                timestamp = start_time + duration * padding + usable_duration * ratio
                timestamps.append(timestamp)
            
            return timestamps
    
    def _extract_frame_at_timestamp(self, cap: cv2.VideoCapture, timestamp: float, 
                                   fps: float) -> Optional[np.ndarray]:
        """
        Extract a single frame at the specified timestamp
        
        Args:
            cap: OpenCV VideoCapture object
            timestamp: Timestamp in seconds
            fps: Frames per second
            
        Returns:
            Frame as numpy array or None if extraction fails
        """
        try:
            frame_number = int(timestamp * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            
            ret, frame = cap.read()
            if not ret or frame is None:
                logger.warning(f"[KEYFRAME_EXTRACTOR] Could not read frame at timestamp {timestamp}")
                return None
            
            return frame
            
        except Exception as e:
            logger.warning(f"[KEYFRAME_EXTRACTOR] Frame extraction failed at {timestamp}s: {e}")
            return None
    
    def _process_frame(self, frame: np.ndarray) -> np.ndarray:
        """
        Process and optimize frame for classification
        
        Args:
            frame: Raw frame from video
            
        Returns:
            Processed frame
        """
        try:
            # Resize frame to target resolution if needed
            height, width = frame.shape[:2]
            target_width, target_height = self.target_resolution
            
            if width > target_width or height > target_height:
                # Calculate scaling factor to maintain aspect ratio
                scale_w = target_width / width
                scale_h = target_height / height
                scale = min(scale_w, scale_h)
                
                new_width = int(width * scale)
                new_height = int(height * scale)
                
                frame = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
            
            # Optional: Apply slight sharpening for better classification
            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
            frame = cv2.filter2D(frame, -1, kernel)
            
            return frame
            
        except Exception as e:
            logger.warning(f"[KEYFRAME_EXTRACTOR] Frame processing failed: {e}")
            return frame  # Return original frame as fallback
    
    def _upload_keyframe_to_gcs(self, frame: np.ndarray, user_id: str, project_id: str,
                               clip_id: str, keyframe_index: int) -> Optional[str]:
        """
        Upload keyframe to Google Cloud Storage
        
        Args:
            frame: Processed frame as numpy array
            user_id: User ID
            project_id: Project ID
            clip_id: Clip identifier
            keyframe_index: Index of keyframe within clip
            
        Returns:
            GCS URI of uploaded keyframe or None if upload fails
        """
        try:
            # Create temporary file for the keyframe
            with NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_keyframe_path = temp_file.name
            
            try:
                # Save frame as JPEG
                cv2.imwrite(
                    temp_keyframe_path, 
                    frame, 
                    [cv2.IMWRITE_JPEG_QUALITY, self.keyframe_quality]
                )
                
                # Generate GCS path
                keyframe_filename = f"{clip_id}_keyframe_{keyframe_index:02d}.jpg"
                gcs_path = f"users/{user_id}/projects/{project_id}/keyframes/{keyframe_filename}"
                
                # Upload to GCS
                gcs_uri = StorageManager.upload_file_to_gcs(temp_keyframe_path, gcs_path)
                
                logger.debug(f"[KEYFRAME_EXTRACTOR] Uploaded keyframe to: {gcs_uri}")
                return gcs_uri
                
            finally:
                # Clean up temporary keyframe file
                if os.path.exists(temp_keyframe_path):
                    os.unlink(temp_keyframe_path)
                    
        except Exception as e:
            logger.error(f"[KEYFRAME_EXTRACTOR] Failed to upload keyframe {keyframe_index} for clip {clip_id}: {e}")
            return None
    
    def cleanup_keyframes_for_project(self, user_id: str, project_id: str):
        """
        Clean up all keyframes for a project (useful for testing/cleanup)
        
        Args:
            user_id: User ID
            project_id: Project ID
        """
        try:
            keyframes_path = f"users/{user_id}/projects/{project_id}/keyframes/"
            StorageManager.delete_blobs_with_prefix(keyframes_path)
            logger.info(f"[KEYFRAME_EXTRACTOR] Cleaned up keyframes for project {project_id}")
            
        except Exception as e:
            logger.error(f"[KEYFRAME_EXTRACTOR] Failed to cleanup keyframes: {e}")
    
    def get_keyframe_stats(self, keyframes: List[Keyframe]) -> dict:
        """
        Get statistics about extracted keyframes
        
        Args:
            keyframes: List of Keyframe objects
            
        Returns:
            Dictionary with keyframe statistics
        """
        if not keyframes:
            return {"count": 0}
        
        return {
            "count": len(keyframes),
            "timestamps": [kf.timestamp for kf in keyframes],
            "positions": [kf.position for kf in keyframes],
            "hero_candidates": sum(1 for kf in keyframes if kf.is_hero_candidate),
            "time_span": max(kf.timestamp for kf in keyframes) - min(kf.timestamp for kf in keyframes)
        }
