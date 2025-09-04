"""
Consolidated Video Classification Manager
Integrates Google Video Intelligence API + Google Vision API with ADR-002 optimizations
"""

import os
import json
import time
import tempfile
import subprocess
import statistics
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from pathlib import Path

from google.cloud import videointelligence_v1 as videointelligence
from google.cloud import vision_v1 as vision
from google.cloud import storage
from google.oauth2 import service_account

from logger import logger
from config.config import settings
from classification.storage import VideoSceneBuckets
from classification.image_classification_manager import ImageClassificationManager
from classification.types.media_models import VideoMedia
from gcp.storage import StorageManager


class VideoClassificationManager:
    """
    Consolidated video classification manager implementing ADR-002 optimizations.
    Combines Google Video Intelligence API for scene detection with Google Vision API 
    for detailed keyframe analysis in a single streamlined service.
    """
    
    def __init__(self):
        """Initialize the consolidated video classification manager"""
        # Set up Google Cloud credentials
        self.credentials = None
        service_account_path = 'secrets/editora-prod-f0da3484f1a0.json'
        if os.path.exists(service_account_path):
            self.credentials = service_account.Credentials.from_service_account_file(
                service_account_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
        
        # Initialize Google Cloud clients
        self.video_intelligence_client = videointelligence.VideoIntelligenceServiceClient(
            credentials=self.credentials
        )
        self.vision_client = vision.ImageAnnotatorClient(credentials=self.credentials)
        self.storage_client = storage.Client(credentials=self.credentials)
        
        # Initialize existing image classifier for category consistency
        self.image_classifier = ClassificationManager()
        self.model = self.image_classifier.model  # Reuse same categories as images
        
        # Load enhanced room mapping
        self.room_mapping = self._load_room_mapping()
        
        logger.info("[VIDEO_CLASSIFIER] Consolidated video classification manager initialized")
    
    def _load_room_mapping(self) -> Dict[str, List[str]]:
        """Load the enhanced room mapping from JSON file"""
        mapping_path = Path(__file__).parent.parent / "utils" / "video_classification_room_mapping.json"
        
        try:
            with open(mapping_path, 'r') as f:
                mapping = json.load(f)
            logger.info(f"[VIDEO_CLASSIFIER] Loaded room mapping with {len(mapping)} room types")
            return mapping
        except Exception as e:
            logger.error(f"[VIDEO_CLASSIFIER] Failed to load room mapping: {e}")
            return {}
    
    def classify_videos(self, videos: List[VideoMedia], user_id: str, project_id: str) -> VideoSceneBuckets:
        """
        Main entry point for consolidated video classification using ADR-002 optimizations
        
        Args:
            videos: List of VideoMedia objects to classify
            user_id: User ID for storage context
            project_id: Project ID for storage context
            
        Returns:
            VideoSceneBuckets with streamlined scene classification results
        """
        logger.info(f"[VIDEO_CLASSIFIER] Starting consolidated classification of {len(videos)} videos")
        start_time = time.time()
        
        # Initialize results
        video_buckets = VideoSceneBuckets()
        video_buckets.google_video_intelligence_used = True
        video_buckets.google_vision_api_used = True
        
        processing_summary = {
            "total_videos_processed": 0,
            "total_scenes_detected": 0,
            "keyframes_extracted": 0,
            "vision_api_calls": 0,
            "scenes_refined_by_vision": 0,
            "cost_estimate": 0.0,
            "processing_time": 0.0
        }
        
        try:
            for video in videos:
                logger.info(f"[VIDEO_CLASSIFIER] Processing video: {video.uri}")
                video_start_time = time.time()
                
                # Step 1: Analyze video with Google Video Intelligence API (ADR-002 config)
                raw_scenes = self._analyze_with_video_intelligence(video.uri)
                if not raw_scenes:
                    logger.warning(f"[VIDEO_CLASSIFIER] No scenes detected for video: {video.uri}")
                    continue
                
                # Step 2: Apply ADR-002 intelligent filtering and consolidation
                filtered_scenes = self._apply_adr002_filtering(raw_scenes)
                consolidated_scenes = self._consolidate_scenes_by_time_windows(filtered_scenes, video.duration or 0)
                
                if not consolidated_scenes:
                    logger.warning(f"[VIDEO_CLASSIFIER] No scenes survived filtering for video: {video.uri}")
                    continue
                
                # Step 3: Extract keyframes for top scenes (cost control)
                scenes_with_keyframes = self._extract_keyframes_for_scenes(
                    video.uri, consolidated_scenes, user_id, project_id
                )
                
                # Step 4: Analyze keyframes with Google Vision API
                vision_enhanced_scenes = self._analyze_keyframes_with_vision(scenes_with_keyframes)
                
                # Step 5: Apply hybrid classification rules and create scene buckets
                final_scenes = self._apply_hybrid_classification_rules(vision_enhanced_scenes)
                self._add_scenes_to_buckets(video_buckets, final_scenes, video.uri)
                
                # Update processing summary
                processing_summary["total_videos_processed"] += 1
                processing_summary["total_scenes_detected"] += len(final_scenes)
                processing_summary["keyframes_extracted"] += len(scenes_with_keyframes)
                processing_summary["vision_api_calls"] += len(scenes_with_keyframes)
                processing_summary["scenes_refined_by_vision"] += len([s for s in final_scenes if s.get("detection_source") == "vision_api"])
                processing_summary["cost_estimate"] += len(scenes_with_keyframes) * 0.0015  # $1.50 per 1000 images
                
                video_processing_time = time.time() - video_start_time
                logger.info(f"[VIDEO_CLASSIFIER] Processed video in {video_processing_time:.2f}s with {len(final_scenes)} scenes")
            
            # Finalize results
            processing_summary["processing_time"] = time.time() - start_time
            video_buckets.processing_summary = processing_summary
            video_buckets.total_scenes = sum(len(scenes) for scenes in video_buckets.buckets.values())
            video_buckets.sort_scenes_by_confidence()
            
            logger.success(f"[VIDEO_CLASSIFIER] Consolidated classification completed: "
                         f"{video_buckets.total_scenes} scenes across {len(video_buckets.get_categories())} categories "
                         f"in {processing_summary['processing_time']:.2f}s")
            
            return video_buckets
            
        except Exception as e:
            logger.error(f"[VIDEO_CLASSIFIER] Consolidated classification failed: {e}")
            # Return empty buckets with error info
            video_buckets.processing_summary = {**processing_summary, "error": str(e)}
            return video_buckets
    
    def _analyze_with_video_intelligence(self, video_uri: str) -> List[Dict[str, Any]]:
        """
        Analyze video with Google Video Intelligence API using ADR-002 optimized configuration
        
        Args:
            video_uri: GCS URI of the video to analyze
            
        Returns:
            List of raw scene data from Video Intelligence API
        """
        logger.info(f"[VIDEO_CLASSIFIER] Analyzing video with Video Intelligence API: {video_uri}")
        
        # ADR-002 optimized configuration
        config = {
            "use_label_detection": True,
            "label_detection_mode": "SHOT_AND_FRAME_MODE",
            "model": "builtin/stable",
            "video_confidence_threshold": 0.6,   # Inclusive for complex scenes
            "frame_confidence_threshold": 0.7,   # Balanced for temporal evidence
            "use_shot_detection": True,
            "shot_detection_model": "builtin/stable"
        }
        
        try:
            # Configure Video Intelligence API request
            features = [videointelligence.Feature.LABEL_DETECTION, videointelligence.Feature.SHOT_CHANGE_DETECTION]
            
            video_context = {
                "label_detection_config": {
                    "label_detection_mode": getattr(videointelligence.LabelDetectionMode, config["label_detection_mode"]),
                    "model": config["model"],
                    "frame_confidence_threshold": config["frame_confidence_threshold"],
                    "video_confidence_threshold": config["video_confidence_threshold"]
                },
                "shot_change_detection_config": {
                    "model": config["shot_detection_model"]
                }
            }
            
            # Make API request
            operation = self.video_intelligence_client.annotate_video(
                request={
                    "input_uri": video_uri,
                    "features": features,
                    "video_context": video_context
                }
            )
            
            logger.info(f"[VIDEO_CLASSIFIER] Processing video with Video Intelligence API...")
            result = operation.result(timeout=600)  # 10 minute timeout
            
            # Extract raw scene data
            raw_scenes = []
            for annotation_result in result.annotation_results:
                # Process frame labels for scene detection
                if annotation_result.frame_label_annotations:
                    for label_annotation in annotation_result.frame_label_annotations:
                        for frame in label_annotation.frames:
                            time_offset = frame.time_offset.seconds + frame.time_offset.microseconds / 1e6
                            raw_scenes.append({
                                "description": label_annotation.entity.description,
                                "confidence": frame.confidence,
                                "time_offset": time_offset,
                                "entity_id": label_annotation.entity.entity_id
                            })
            
            logger.info(f"[VIDEO_CLASSIFIER] Video Intelligence API detected {len(raw_scenes)} raw scene labels")
            return raw_scenes
            
        except Exception as e:
            logger.error(f"[VIDEO_CLASSIFIER] Video Intelligence API analysis failed: {e}")
            return []
    
    def _apply_adr002_filtering(self, raw_scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply ADR-002 intelligent label filtering and prioritization"""
        logger.debug(f"[VIDEO_CLASSIFIER] Applying ADR-002 filtering to {len(raw_scenes)} raw scenes")
        
        # ADR-002 filtering categories
        specific_scene_keywords = {
            'bedroom', 'bathroom', 'kitchen', 'living room', 'dining room', 'office', 
            'hallway', 'corridor', 'lobby', 'entrance', 'foyer', 'balcony', 'patio',
            'garden', 'yard', 'outdoor', 'pool', 'swimming pool', 'swimming', 'deck', 
            'terrace', 'garage', 'closet', 'pantry', 'basement', 'attic'
        }
        
        generic_scene_keywords = {
            'room', 'interior', 'space', 'area', 'zone', 'chamber', 'suite', 'studio', 'loft'
        }
        
        excluded_generic_labels = {
            'floor', 'property', 'wall', 'flooring', 'furniture', 'table', 'chair', 
            'ceiling', 'tile', 'wood', 'stone', 'countertop', 'cabinet', 'door', 'window'
        }
        
        filtered_scenes = []
        for scene in raw_scenes:
            description_lower = scene['description'].lower()
            confidence = scene['confidence']
            
            # Apply filtering logic
            is_specific_scene = any(keyword in description_lower for keyword in specific_scene_keywords)
            is_generic_scene = any(keyword in description_lower for keyword in generic_scene_keywords)
            is_excluded_generic = any(keyword in description_lower for keyword in excluded_generic_labels)
            
            should_include = False
            priority = 3  # Default low priority
            
            if is_specific_scene and confidence >= 0.6:
                should_include = True
                priority = 1  # Highest priority
            elif is_generic_scene and confidence >= 0.8 and not is_excluded_generic:
                should_include = True
                priority = 2  # Medium priority
            elif is_excluded_generic and confidence >= 0.95:
                should_include = True
                priority = 3  # Low priority (only for extremely high confidence)
            
            if should_include:
                scene['priority'] = priority
                scene['filter_reason'] = 'specific_scene' if priority == 1 else 'generic_scene' if priority == 2 else 'high_confidence_generic'
                filtered_scenes.append(scene)
        
        logger.debug(f"[VIDEO_CLASSIFIER] ADR-002 filtering: {len(raw_scenes)} → {len(filtered_scenes)} scenes")
        return filtered_scenes
    
    def _consolidate_scenes_by_time_windows(self, filtered_scenes: List[Dict[str, Any]], video_duration: float) -> List[Dict[str, Any]]:
        """Apply ADR-002 time-window consolidation with priority resolution"""
        if not filtered_scenes:
            return []
        
        logger.debug(f"[VIDEO_CLASSIFIER] Consolidating {len(filtered_scenes)} scenes by time windows")
        
        # Group scenes by 1-second time windows
        time_windows = defaultdict(list)
        for scene in filtered_scenes:
            time_key = int(scene['time_offset'])
            time_windows[time_key].append(scene)
        
        # For each time window, select the best scene indicator (priority resolution)
        consolidated_frames = []
        for time_key, scenes_at_time in time_windows.items():
            # Sort by priority (1 = specific scene first) then by confidence
            scenes_at_time.sort(key=lambda x: (x['priority'], -x['confidence']))
            best_scene = scenes_at_time[0]  # Take highest priority scene
            consolidated_frames.append(best_scene)
        
        # Group consolidated frames by scene description
        scene_groups = defaultdict(list)
        for frame in consolidated_frames:
            scene_groups[frame['description']].append(frame)
        
        # Create consolidated scenes
        consolidated_scenes = []
        for description, frames in scene_groups.items():
            if len(frames) < 1:  # Need at least 1 frame
                continue
                
            frames.sort(key=lambda x: x['time_offset'])
            
            start_time = frames[0]['time_offset']
            end_time = frames[-1]['time_offset']
            
            # Expand boundaries for single frame scenes
            if len(frames) == 1:
                start_time = max(0, start_time - 2.0)
                end_time = min(video_duration, end_time + 2.0)
            
            avg_confidence = statistics.mean([f['confidence'] for f in frames])
            priority = frames[0]['priority']
            
            consolidated_scenes.append({
                'scene_type': description,
                'start_time': start_time,
                'end_time': end_time,
                'duration': end_time - start_time,
                'confidence': avg_confidence,
                'keyframe_timestamp': (start_time + end_time) / 2,
                'frame_count': len(frames),
                'priority': priority
            })
        
        # Sort by priority then by confidence
        consolidated_scenes.sort(key=lambda x: (x['priority'], -x['confidence']))
        
        logger.debug(f"[VIDEO_CLASSIFIER] Consolidated into {len(consolidated_scenes)} scenes")
        return consolidated_scenes
    
    def _extract_keyframes_for_scenes(self, video_uri: str, scenes: List[Dict[str, Any]], 
                                    user_id: str, project_id: str) -> List[Dict[str, Any]]:
        """Extract keyframes for top scenes using FFmpeg with ADR-002 cost control"""
        if not scenes:
            return []
        
        # ADR-002 cost control: limit to top 10 scenes by confidence
        top_scenes = sorted(scenes, key=lambda x: x['confidence'], reverse=True)[:10]
        high_confidence_scenes = [s for s in top_scenes if s['confidence'] >= 0.7]
        
        logger.info(f"[VIDEO_CLASSIFIER] Extracting keyframes for {len(high_confidence_scenes)} high-confidence scenes")
        
        scenes_with_keyframes = []
        bucket_name = settings.GCP.Storage.USER_BUCKET
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Download video locally for FFmpeg processing
            local_video_path = temp_dir_path / "video.mp4"
            self._download_video_from_gcs(video_uri, str(local_video_path))
            
            for scene in high_confidence_scenes:
                try:
                    timestamp = scene['keyframe_timestamp']
                    scene_id = f"scene_{scene['start_time']:.1f}s"
                    
                    # Extract keyframe using FFmpeg
                    keyframe_filename = f"keyframe_{scene_id}.jpg"
                    local_keyframe_path = temp_dir_path / keyframe_filename
                    
                    success = self._extract_keyframe_with_ffmpeg(
                        str(local_video_path), timestamp, str(local_keyframe_path)
                    )
                    
                    if success:
                        # Upload keyframe to GCS
                        keyframe_blob_name = f"tests/video-intelligence/keyframes/{keyframe_filename}"
                        keyframe_uri = self._upload_keyframe_to_gcs(
                            str(local_keyframe_path), bucket_name, keyframe_blob_name
                        )
                        
                        if keyframe_uri:
                            scene['keyframe_uri'] = keyframe_uri
                            scene['scene_id'] = scene_id
                            scenes_with_keyframes.append(scene)
                            logger.debug(f"[VIDEO_CLASSIFIER] Extracted keyframe for scene {scene_id}")
                
                except Exception as e:
                    logger.warning(f"[VIDEO_CLASSIFIER] Failed to extract keyframe for scene: {e}")
                    continue
        
        logger.info(f"[VIDEO_CLASSIFIER] Successfully extracted {len(scenes_with_keyframes)} keyframes")
        return scenes_with_keyframes
    
    def _download_video_from_gcs(self, video_uri: str, local_path: str):
        """Download video from GCS to local path"""
        # Extract bucket and blob from gs:// URI
        uri_parts = video_uri.replace("gs://", "").split("/", 1)
        bucket_name = uri_parts[0]
        blob_name = uri_parts[1]
        
        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.download_to_filename(local_path)
    
    def _extract_keyframe_with_ffmpeg(self, video_path: str, timestamp: float, output_path: str) -> bool:
        """Extract a single keyframe using FFmpeg"""
        try:
            command = [
                "ffmpeg", "-i", video_path,
                "-ss", str(timestamp),
                "-vframes", "1",
                "-q:v", "2",  # High quality
                output_path,
                "-y"  # Overwrite if exists
            ]
            
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            return result.returncode == 0 and Path(output_path).exists()
            
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return False
    
    def _upload_keyframe_to_gcs(self, local_path: str, bucket_name: str, blob_name: str) -> Optional[str]:
        """Upload keyframe to GCS and return the GCS URI"""
        try:
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(local_path)
            return f"gs://{bucket_name}/{blob_name}"
        except Exception as e:
            logger.error(f"[VIDEO_CLASSIFIER] Failed to upload keyframe: {e}")
            return None
    
    def _analyze_keyframes_with_vision(self, scenes_with_keyframes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze extracted keyframes using Google Vision API with ADR-002 exact match priority"""
        if not scenes_with_keyframes:
            return []
        
        logger.info(f"[VIDEO_CLASSIFIER] Analyzing {len(scenes_with_keyframes)} keyframes with Vision API")
        
        vision_enhanced_scenes = []
        for scene in scenes_with_keyframes:
            try:
                keyframe_uri = scene.get('keyframe_uri')
                if not keyframe_uri:
                    vision_enhanced_scenes.append(scene)
                    continue
                
                # Perform Vision API label detection
                image = vision.Image(source=vision.ImageSource(image_uri=keyframe_uri))
                response = self.vision_client.label_detection(image=image)
                
                # Process labels with confidence >= 0.75
                vision_labels = []
                for label in response.label_annotations:
                    if label.score >= 0.75:
                        vision_labels.append({
                            "description": label.description.lower(),
                            "confidence": label.score
                        })
                
                # Apply ADR-002 exact match priority
                vision_room, vision_confidence = self._match_vision_to_room_with_exact_priority(vision_labels)
                
                # Enhance scene with Vision API results
                scene['vision_labels'] = vision_labels
                scene['vision_room'] = vision_room
                scene['vision_confidence'] = vision_confidence
                
                vision_enhanced_scenes.append(scene)
                
                # Brief pause to respect API limits
                time.sleep(0.1)
                
            except Exception as e:
                logger.warning(f"[VIDEO_CLASSIFIER] Vision API analysis failed for scene: {e}")
                vision_enhanced_scenes.append(scene)  # Add scene without vision enhancement
                continue
        
        logger.info(f"[VIDEO_CLASSIFIER] Vision API analysis completed for {len(vision_enhanced_scenes)} scenes")
        return vision_enhanced_scenes
    
    def _match_vision_to_room_with_exact_priority(self, vision_labels: List[Dict[str, Any]]) -> Tuple[Optional[str], float]:
        """Match Vision API labels to room types with ADR-002 exact match priority"""
        if not vision_labels or not self.room_mapping:
            return None, 0.0
        
        # Priority 1: Check for exact room name matches
        for vision_label in vision_labels:
            description = vision_label['description'].lower()
            confidence = vision_label['confidence']
            
            for room_type in self.room_mapping.keys():
                if description == room_type.lower() or room_type.lower() in description:
                    logger.debug(f"[VIDEO_CLASSIFIER] Exact match: '{description}' → '{room_type}' (confidence: {confidence:.3f})")
                    return room_type, confidence
        
        # Priority 2: Indicator-based matching
        room_scores = defaultdict(list)
        for vision_label in vision_labels:
            description = vision_label['description'].lower()
            confidence = vision_label['confidence']
            
            for room_type, room_indicators in self.room_mapping.items():
                for indicator in room_indicators:
                    if indicator.lower() in description or description in indicator.lower():
                        room_scores[room_type].append(confidence)
        
        # Find the room with highest average confidence
        best_room = None
        best_score = 0.0
        
        for room_type, scores in room_scores.items():
            avg_score = statistics.mean(scores)
            if avg_score > best_score:
                best_score = avg_score
                best_room = room_type
        
        if best_room:
            logger.debug(f"[VIDEO_CLASSIFIER] Indicator match: '{best_room}' (confidence: {best_score:.3f})")
        
        return best_room, best_score
    
    def _apply_hybrid_classification_rules(self, vision_enhanced_scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply ADR-002 hybrid classification rules to determine final scene categories"""
        final_scenes = []
        
        for scene in vision_enhanced_scenes:
            original_type = scene['scene_type']
            original_confidence = scene['confidence']
            vision_room = scene.get('vision_room')
            vision_confidence = scene.get('vision_confidence', 0.0)
            
            # ADR-002 hybrid classification priority rules
            final_category = original_type
            final_confidence = original_confidence
            detection_source = "video_intelligence"
            
            # Priority 1: Vision API exact matches
            if vision_room and vision_confidence >= 0.75:
                final_category = vision_room
                final_confidence = max(original_confidence, vision_confidence)
                detection_source = "vision_api"
                logger.debug(f"[VIDEO_CLASSIFIER] Vision API override: '{original_type}' → '{vision_room}'")
            
            # Priority 2: Keep specific Video Intelligence scenes
            elif self._is_specific_scene_related(original_type):
                detection_source = "video_intelligence"
                logger.debug(f"[VIDEO_CLASSIFIER] Kept Video Intelligence: '{original_type}'")
            
            # Priority 3: Fallback for generic scenes
            else:
                if vision_room:
                    final_category = vision_room
                    final_confidence = vision_confidence
                    detection_source = "vision_api"
                else:
                    detection_source = "fallback"
                    logger.debug(f"[VIDEO_CLASSIFIER] Fallback classification: '{original_type}'")
            
            # Create final scene
            final_scene = {
                'scene_id': scene.get('scene_id', f"scene_{scene['start_time']:.1f}s"),
                'scene_type': final_category,
                'start_time': scene['start_time'],
                'end_time': scene['end_time'],
                'duration': scene['duration'],
                'confidence': final_confidence,
                'detection_source': detection_source,
                'keyframe_uri': scene.get('keyframe_uri'),
                'original_video_intelligence_type': original_type if detection_source != "video_intelligence" else None,
                'vision_labels': scene.get('vision_labels', [])
            }
            
            final_scenes.append(final_scene)
        
        logger.info(f"[VIDEO_CLASSIFIER] Applied hybrid classification rules to {len(final_scenes)} scenes")
        return final_scenes
    
    def _is_specific_scene_related(self, description: str) -> bool:
        """Check if a description is a specific scene type"""
        specific_keywords = {
            'bedroom', 'bathroom', 'kitchen', 'living room', 'dining room', 'office', 
            'outdoor', 'pool', 'swimming pool', 'patio', 'balcony', 'garage'
        }
        return any(keyword in description.lower() for keyword in specific_keywords)
    
    def _add_scenes_to_buckets(self, video_buckets: VideoSceneBuckets, final_scenes: List[Dict[str, Any]], source_video_uri: str):
        """Add final scenes to the video buckets using streamlined storage format"""
        for scene in final_scenes:
            # Map to existing categories or use 'Other'
            category = scene['scene_type']
            if category not in self.model.categories:
                # Try to map to existing categories
                category_mapping = {
                    'living room': 'Interior',
                    'kitchen': 'Interior', 
                    'bedroom': 'Interior',
                    'bathroom': 'Interior',
                    'dining room': 'Interior',
                    'office': 'Interior',
                    'outdoor': 'Exterior',
                    'pool': 'Exterior',
                    'swimming pool': 'Exterior',
                    'patio': 'Exterior',
                    'balcony': 'Exterior'
                }
                category = category_mapping.get(category.lower(), 'Other')
            
            # Create scene item
            scene_item = VideoSceneBuckets.SceneItem(
                scene_id=scene['scene_id'],
                source_video_uri=source_video_uri,
                start_time=scene['start_time'],
                end_time=scene['end_time'],
                confidence=scene['confidence'],
                detection_source=scene['detection_source'],
                keyframe_uri=scene.get('keyframe_uri')
            )
            
            # Add to bucket
            video_buckets.add_scene_to_bucket(category, scene_item)
        
        logger.debug(f"[VIDEO_CLASSIFIER] Added {len(final_scenes)} scenes to buckets")
