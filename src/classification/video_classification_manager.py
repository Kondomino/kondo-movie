"""
Enhanced Video Classification Manager
Implements advanced scene detection with hierarchical room priority system
Based on proven logic from test_google_video_intelligence_raw.py
"""

import os
import json
import time
import tempfile
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from google.cloud import videointelligence_v1 as videointelligence
from google.cloud import storage
from google.oauth2 import service_account

from logger import logger
from config.config import settings
from classification.storage.video_scene_storage import VideoScenesStorage
from classification.types.media_models import VideoMedia
from gcp.storage import StorageManager


class VideoClassificationManager:
    """
    Enhanced video classification manager with hierarchical room priority system.
    Provides accurate scene detection and intelligent scene segmentation.
    """
    
    def __init__(self):
        """Initialize the enhanced video classification manager"""
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
        
        # Room priority hierarchy (from our successful test)
        self.room_priority = {
            # Tier 1: Highly specific rooms (highest priority)
            'kitchen': {'priority': 10, 'type': 'indoor', 'subtype': 'kitchen'},
            'bedroom': {'priority': 10, 'type': 'indoor', 'subtype': 'bedroom'},
            'bathroom': {'priority': 10, 'type': 'indoor', 'subtype': 'bathroom'},
            'living room': {'priority': 10, 'type': 'indoor', 'subtype': 'living_room'},
            'dining room': {'priority': 10, 'type': 'indoor', 'subtype': 'dining_room'},
            'home office': {'priority': 10, 'type': 'indoor', 'subtype': 'office'},
            'office': {'priority': 9, 'type': 'indoor', 'subtype': 'office'},
            
            # Tier 2: Specific outdoor areas
            'swimming pool': {'priority': 9, 'type': 'outdoor', 'subtype': 'pool_area'},
            'patio': {'priority': 8, 'type': 'outdoor', 'subtype': 'patio'},
            'balcony': {'priority': 8, 'type': 'outdoor', 'subtype': 'balcony'},
            'garden': {'priority': 8, 'type': 'outdoor', 'subtype': 'garden'},
            
            # Tier 3: Moderately specific
            'outdoor furniture': {'priority': 6, 'type': 'outdoor', 'subtype': 'outdoor_generic'},
            'room': {'priority': 5, 'type': 'indoor', 'subtype': 'interior_generic'},
            'interior design': {'priority': 4, 'type': 'indoor', 'subtype': 'interior_generic'},
            
            # Tier 4: Generic (lowest priority)
            'outdoor': {'priority': 3, 'type': 'outdoor', 'subtype': 'outdoor_generic'},
            'indoor': {'priority': 3, 'type': 'indoor', 'subtype': 'interior_generic'},
            'property': {'priority': 1, 'type': 'generic', 'subtype': 'property'},
            'space': {'priority': 2, 'type': 'generic', 'subtype': 'space'}
        }
    
    def classify_videos(self, videos: List[VideoMedia], user_id: str, project_id: str) -> Dict[str, Any]:
        """
        Main entry point for enhanced video classification using new storage system.
        
        Args:
            videos: List of video media objects
            user_id: User ID
            project_id: Project ID
            
        Returns:
            Dictionary with classification results and statistics
        """
        logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Starting classification for {len(videos)} videos")
        
        processing_summary = {
            "total_videos_processed": 0,
            "total_scenes_detected": 0,
            "processing_time": 0.0,
            "enhanced_detection": True,
            "room_priority_system": True,
            "videos_processed": []
        }
        
        start_time = time.time()
        
        try:
            for video in videos:
                logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Processing video: {video.uri}")
                video_start_time = time.time()
                
                # Step 1: Analyze video with Google Video Intelligence API
                raw_results = self.analyze_video_raw_labels(video.uri)
                if not raw_results or not raw_results.get("frame_labels"):
                    logger.warning(f"[ENHANCED_VIDEO_CLASSIFIER] No labels detected for video: {video.uri}")
                    continue
                
                # Step 2: Apply enhanced scene detection with hierarchical room priority
                final_scenes = self._apply_enhanced_scene_detection(
                    raw_results["frame_labels"], 
                    raw_results["video_duration"]
                )
                
                if not final_scenes:
                    logger.warning(f"[ENHANCED_VIDEO_CLASSIFIER] No scenes survived enhanced detection for video: {video.uri}")
                    continue
                
                # Step 3: Store enhanced scene classifications using new storage system
                success = self._store_video_scene_classification_new(
                    user_id, project_id, video.uri, final_scenes, raw_results
                )
                
                # Update processing summary
                processing_summary["total_videos_processed"] += 1
                processing_summary["total_scenes_detected"] += len(final_scenes)
                processing_summary["videos_processed"].append({
                    "video_uri": video.uri,
                    "scenes_detected": len(final_scenes),
                    "processing_time": time.time() - video_start_time,
                    "storage_success": success
                })
                
                video_processing_time = time.time() - video_start_time
                logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Completed video {video.uri} in {video_processing_time:.2f}s with {len(final_scenes)} scenes")
        
        except Exception as e:
            logger.error(f"[ENHANCED_VIDEO_CLASSIFIER] Classification failed: {e}")
            raise
        
        finally:
            processing_summary["processing_time"] = time.time() - start_time
            logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Processing summary: {processing_summary}")
        
        return processing_summary
    
    def analyze_video_raw_labels(self, video_uri: str) -> Dict[str, Any]:
        """
        Analyze video with Google Video Intelligence API and return raw results.
        Ported from test_google_video_intelligence_raw.py
        
        Args:
            video_uri: GCS URI of video to analyze
            
        Returns:
            Dictionary containing raw API results
        """
        logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Analyzing video with Google Video Intelligence API: {video_uri}")
        
        # Configure Video Intelligence API request (same as successful test)
        features = [
            videointelligence.Feature.LABEL_DETECTION,
            videointelligence.Feature.SHOT_CHANGE_DETECTION
        ]
        
        video_context = {
            "label_detection_config": {
                "label_detection_mode": videointelligence.LabelDetectionMode.SHOT_AND_FRAME_MODE,
                "model": "builtin/stable",
                "video_confidence_threshold": 0.5,
                "frame_confidence_threshold": 0.5
            },
            "shot_change_detection_config": {
                "model": "builtin/stable"
            }
        }

        # Make the API request
        operation = self.video_intelligence_client.annotate_video(
            request={
                "input_uri": video_uri,
                "features": features,
                "video_context": video_context
            }
        )

        logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Processing video with Google Video Intelligence API...")
        result = operation.result(timeout=600)  # 10 minute timeout

        # Process and structure results (same format as test)
        raw_results = {
            "video_uri": video_uri,
            "processing_timestamp": datetime.utcnow().isoformat(),
            "frame_labels": [],
            "segment_labels": [],
            "shot_annotations": [],
            "video_duration": 0,
            "api_config": {
                "features": ["LABEL_DETECTION", "SHOT_CHANGE_DETECTION"],
                "label_detection_mode": "SHOT_AND_FRAME_MODE",
                "model": "builtin/stable",
                "video_confidence_threshold": 0.5,
                "frame_confidence_threshold": 0.5
            }
        }
        
        for annotation_result in result.annotation_results:
            # Process shot annotations
            if annotation_result.shot_annotations:
                for i, shot in enumerate(annotation_result.shot_annotations):
                    start_time = (shot.start_time_offset.seconds + 
                                shot.start_time_offset.microseconds / 1e6)
                    end_time = (shot.end_time_offset.seconds + 
                              shot.end_time_offset.microseconds / 1e6)
                    
                    raw_results["shot_annotations"].append({
                        "shot_number": i+1,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": end_time - start_time
                    })
                    
                    raw_results["video_duration"] = max(raw_results["video_duration"], end_time)
            
            # Process segment labels
            if annotation_result.segment_label_annotations:
                for label_annotation in annotation_result.segment_label_annotations:
                    label_data = {
                        "description": label_annotation.entity.description,
                        "entity_id": label_annotation.entity.entity_id,
                        "max_confidence": max(segment.confidence for segment in label_annotation.segments),
                        "segments": []
                    }
                    
                    for segment in label_annotation.segments:
                        start_time = (segment.segment.start_time_offset.seconds + 
                                    segment.segment.start_time_offset.microseconds / 1e6)
                        end_time = (segment.segment.end_time_offset.seconds + 
                                  segment.segment.end_time_offset.microseconds / 1e6)
                        
                        label_data["segments"].append({
                            "start_time": start_time,
                            "end_time": end_time,
                            "confidence": segment.confidence
                        })
                    
                    raw_results["segment_labels"].append(label_data)

            # Process frame labels (most important for our enhanced detection)
            if annotation_result.frame_label_annotations:
                for label_annotation in annotation_result.frame_label_annotations:
                    label_data = {
                        "description": label_annotation.entity.description,
                        "entity_id": label_annotation.entity.entity_id,
                        "max_confidence": max(frame.confidence for frame in label_annotation.frames),
                        "frame_count": len(label_annotation.frames),
                        "frames": []
                    }
                    
                    for frame in label_annotation.frames:
                        time_offset = (frame.time_offset.seconds + 
                                     frame.time_offset.microseconds / 1e6)
                        
                        label_data["frames"].append({
                            "time_offset": time_offset,
                            "confidence": frame.confidence
                        })
                    
                    raw_results["frame_labels"].append(label_data)

        logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Extracted {len(raw_results['frame_labels'])} frame labels and {len(raw_results['segment_labels'])} segment labels")
        return raw_results
    
    def _apply_enhanced_scene_detection(self, frame_labels: List[Dict[str, Any]], video_duration: float) -> List[Dict[str, Any]]:
        """
        Apply our proven enhanced scene detection pipeline.
        Ported from test_google_video_intelligence_raw.py
        
        Args:
            frame_labels: Frame labels from Google Video Intelligence
            video_duration: Total video duration in seconds
            
        Returns:
            List of final consolidated scenes
        """
        logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Applying enhanced scene detection...")
        
        # Step 1: Detect scene boundaries using timeline analysis
        scenes = self.detect_scene_boundaries(frame_labels, video_duration)
        
        # Step 2: Apply hierarchical room priority and segmentation
        refined_scenes = self.prioritize_and_segment_scenes(scenes)
        
        # Step 3: Consolidate micro-scenes into final coherent scenes
        final_scenes = self.consolidate_final_scenes(refined_scenes, video_duration)
        
        logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Enhanced scene detection completed: {len(final_scenes)} final scenes")
        return final_scenes
    
    def detect_scene_boundaries(self, frame_labels: List[Dict[str, Any]], video_duration: float) -> List[Dict[str, Any]]:
        """
        Detect natural scene boundaries by analyzing label transitions and temporal patterns.
        Ported from test_google_video_intelligence_raw.py
        """
        # Create timeline grid (1-second intervals)
        timeline_grid = {}
        for timestamp in range(int(video_duration) + 1):
            timeline_grid[float(timestamp)] = []
        
        # Map all labels to timeline positions
        for label_data in frame_labels:
            description = label_data['description']
            for frame in label_data['frames']:
                time_key = float(int(frame['time_offset']))  # Round to nearest second
                if time_key in timeline_grid:
                    timeline_grid[time_key].append({
                        'label': description,
                        'confidence': frame['confidence'],
                        'exact_time': frame['time_offset']
                    })
        
        # Create label signatures for each time point
        label_signatures = {}
        for timestamp, labels in timeline_grid.items():
            if labels:
                # Group by label and calculate average confidence
                label_groups = {}
                for label_info in labels:
                    label = label_info['label']
                    if label not in label_groups:
                        label_groups[label] = []
                    label_groups[label].append(label_info['confidence'])
                
                # Create signature with average confidences
                signature = {}
                for label, confidences in label_groups.items():
                    signature[label] = sum(confidences) / len(confidences)
                
                label_signatures[timestamp] = signature
            else:
                label_signatures[timestamp] = {}
        
        # Detect transition points
        transitions = []
        timestamps = sorted(label_signatures.keys())
        
        for i in range(1, len(timestamps)):
            prev_timestamp = timestamps[i-1]
            curr_timestamp = timestamps[i]
            
            prev_signature = label_signatures[prev_timestamp]
            curr_signature = label_signatures[curr_timestamp]
            
            similarity = self.calculate_signature_similarity(prev_signature, curr_signature)
            
            # Transition threshold - lower means more sensitive to changes
            if similarity < 0.4 and (prev_signature or curr_signature):  # At least one non-empty
                transitions.append({
                    'timestamp': curr_timestamp,
                    'transition_strength': 1 - similarity,
                    'old_labels': prev_signature,
                    'new_labels': curr_signature
                })
        
        # Group consecutive time periods into scenes
        scenes = []
        current_scene_start = 0.0
        
        for transition in transitions + [{'timestamp': video_duration}]:  # Add end marker
            scene_end = transition['timestamp']
            
            if scene_end > current_scene_start:
                # Collect all labels in this scene period
                scene_label_data = {}
                for timestamp in range(int(current_scene_start), int(scene_end) + 1):
                    ts_key = float(timestamp)
                    if ts_key in label_signatures:
                        for label, confidence in label_signatures[ts_key].items():
                            if label not in scene_label_data:
                                scene_label_data[label] = []
                            scene_label_data[label].append(confidence)
                
                if scene_label_data:  # Only create scene if it has labels
                    # Calculate average confidences for the scene
                    scene_labels = {}
                    for label, confidences in scene_label_data.items():
                        scene_labels[label] = {
                            'avg_confidence': sum(confidences) / len(confidences),
                            'max_confidence': max(confidences),
                            'frame_count': len(confidences)
                        }
                    
                    scene = {
                        'scene_id': len(scenes) + 1,
                        'start_time': current_scene_start,
                        'end_time': scene_end,
                        'duration': scene_end - current_scene_start,
                        'labels': scene_labels,
                        'dominant_label': max(scene_labels.items(), key=lambda x: x[1]['avg_confidence'])[0] if scene_labels else 'unknown'
                    }
                    scenes.append(scene)
            
            current_scene_start = scene_end
        
        return scenes
    
    def calculate_signature_similarity(self, sig1: Dict[str, float], sig2: Dict[str, float]) -> float:
        """
        Calculate similarity between two label signatures.
        Ported from test_google_video_intelligence_raw.py
        """
        if not sig1 and not sig2:
            return 1.0
        if not sig1 or not sig2:
            return 0.0
        
        # Get all unique labels
        all_labels = set(sig1.keys()) | set(sig2.keys())
        
        if not all_labels:
            return 1.0
        
        # Calculate weighted similarity
        similarity_sum = 0.0
        weight_sum = 0.0
        
        for label in all_labels:
            conf1 = sig1.get(label, 0.0)
            conf2 = sig2.get(label, 0.0)
            
            # Weight by maximum confidence (more important labels have more influence)
            weight = max(conf1, conf2)
            
            # Similarity for this label (1.0 if both present, 0.0 if only one present)
            if conf1 > 0 and conf2 > 0:
                label_similarity = 1.0 - abs(conf1 - conf2)  # Confidence difference
            else:
                label_similarity = 0.0
            
            similarity_sum += label_similarity * weight
            weight_sum += weight
        
        return similarity_sum / weight_sum if weight_sum > 0 else 0.0
    
    def prioritize_and_segment_scenes(self, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply hierarchical room priority and segment scenes based on specific room detections.
        Ported from test_google_video_intelligence_raw.py
        """
        refined_scenes = []
        
        for scene in scenes:
            # Find highest priority labels in this scene
            scene_labels = scene['labels']
            priority_labels = []
            
            for label, data in scene_labels.items():
                priority_info = self.get_label_priority(label)
                if priority_info:
                    priority_labels.append({
                        'label': label,
                        'priority': priority_info['priority'],
                        'type': priority_info['type'],
                        'subtype': priority_info['subtype'],
                        'confidence': data['avg_confidence'],
                        'frame_count': data['frame_count']
                    })
            
            # Sort by priority (highest first), then by confidence
            priority_labels.sort(key=lambda x: (x['priority'], x['confidence']), reverse=True)
            
            if not priority_labels:
                # No recognized labels, keep as generic scene
                refined_scenes.append(scene)
                continue
            
            # Check if we need to segment this scene
            high_priority_labels = [l for l in priority_labels if l['priority'] >= 9]  # Tier 1 & high Tier 2
            
            if len(high_priority_labels) > 1:
                # Multiple high-priority labels - need to segment
                segmented_scenes = self.segment_scene_by_priority(scene, high_priority_labels, scene_labels)
                refined_scenes.extend(segmented_scenes)
            else:
                # Single dominant label or no high-priority conflicts
                dominant_label = priority_labels[0]
                
                # Update scene classification
                scene['scene_type'] = dominant_label['subtype']
                scene['scene_category'] = dominant_label['type']
                scene['primary_label'] = dominant_label['label']
                scene['scene_confidence'] = self.calculate_scene_confidence(scene, dominant_label)
                
                refined_scenes.append(scene)
        
        return refined_scenes
    
    def get_label_priority(self, label: str) -> Optional[Dict[str, Any]]:
        """
        Get priority information for a label with fuzzy matching.
        Ported from test_google_video_intelligence_raw.py
        """
        label_lower = label.lower()
        
        # Direct match
        if label_lower in self.room_priority:
            return self.room_priority[label_lower]
        
        # Fuzzy matching for compound labels
        for priority_label, info in self.room_priority.items():
            if priority_label in label_lower or label_lower in priority_label:
                return info
        
        # Check for partial matches with high-priority rooms
        high_priority_keywords = {
            'kitchen': ['kitchen', 'cook', 'stove', 'refrigerator'],
            'bedroom': ['bedroom', 'bed', 'sleep'],
            'bathroom': ['bathroom', 'bath', 'toilet', 'shower'],
            'living room': ['living', 'sofa', 'couch', 'tv', 'television'],
            'office': ['office', 'desk', 'computer', 'workspace'],
            'swimming pool': ['pool', 'swim']
        }
        
        for room, keywords in high_priority_keywords.items():
            if any(keyword in label_lower for keyword in keywords):
                return self.room_priority.get(room, None)
        
        return None
    
    def segment_scene_by_priority(self, scene: Dict[str, Any], high_priority_labels: List[Dict], 
                                all_scene_labels: Dict[str, Dict]) -> List[Dict[str, Any]]:
        """
        Segment a scene when multiple high-priority room types are detected.
        Ported from test_google_video_intelligence_raw.py
        """
        segmented_scenes = []
        scene_duration = scene['duration']
        num_segments = len(high_priority_labels)
        
        # Simple equal division for now (could be enhanced with temporal analysis)
        segment_duration = scene_duration / num_segments
        
        for i, priority_label in enumerate(high_priority_labels):
            segment_start = scene['start_time'] + (i * segment_duration)
            segment_end = segment_start + segment_duration
            
            # Ensure last segment goes to original end time
            if i == num_segments - 1:
                segment_end = scene['end_time']
            
            segmented_scene = {
                'scene_id': f"{scene['scene_id']}.{i + 1}",
                'start_time': segment_start,
                'end_time': segment_end,
                'duration': segment_end - segment_start,
                'labels': {priority_label['label']: all_scene_labels[priority_label['label']]},
                'scene_type': priority_label['subtype'],
                'scene_category': priority_label['type'],
                'primary_label': priority_label['label'],
                'scene_confidence': priority_label['confidence'],
                'segmentation_reason': f"Split from original scene due to multiple high-priority rooms detected",
                'original_scene_id': scene['scene_id']
            }
            
            segmented_scenes.append(segmented_scene)
        
        return segmented_scenes
    
    def calculate_scene_confidence(self, scene: Dict[str, Any], dominant_label: Dict[str, Any]) -> float:
        """
        Calculate overall confidence score for a scene.
        Ported from test_google_video_intelligence_raw.py
        """
        # Multi-factor confidence calculation
        label_confidence = dominant_label['confidence']  # 50%
        priority_bonus = min(dominant_label['priority'] / 10.0, 1.0)  # 30% - higher priority = more confident
        duration_factor = min(scene['duration'] / 5.0, 1.0)  # 20% - longer scenes = more confident
        
        combined_confidence = (label_confidence * 0.5) + (priority_bonus * 0.3) + (duration_factor * 0.2)
        
        return min(combined_confidence, 1.0)
    
    def consolidate_final_scenes(self, refined_scenes: List[Dict[str, Any]], video_duration: float) -> List[Dict[str, Any]]:
        """
        Consolidate micro-scenes into final coherent scenes for real estate classification.
        Ported from test_google_video_intelligence_raw.py
        """
        # Sort scenes by start time
        sorted_scenes = sorted(refined_scenes, key=lambda x: x['start_time'])
        
        final_scenes = []
        current_scene = None
        
        for scene in sorted_scenes:
            scene_type = scene.get('scene_type', 'unknown')
            scene_category = scene.get('scene_category', 'unknown')
            
            # If this is the same type as current scene and within 5 seconds, merge
            if (current_scene and 
                current_scene['scene_type'] == scene_type and 
                scene['start_time'] - current_scene['end_time'] <= 5.0):
                
                # Merge scenes
                current_scene['end_time'] = scene['end_time']
                current_scene['duration'] = current_scene['end_time'] - current_scene['start_time']
                
                # Merge labels
                for label, data in scene['labels'].items():
                    if label in current_scene['labels']:
                        # Combine frame counts and recalculate confidence
                        old_frames = current_scene['labels'][label]['frame_count']
                        old_conf = current_scene['labels'][label]['avg_confidence']
                        new_frames = data['frame_count']
                        new_conf = data['avg_confidence']
                        
                        total_frames = old_frames + new_frames
                        combined_conf = ((old_conf * old_frames) + (new_conf * new_frames)) / total_frames
                        
                        current_scene['labels'][label] = {
                            'avg_confidence': combined_conf,
                            'max_confidence': max(current_scene['labels'][label]['max_confidence'], data['max_confidence']),
                            'frame_count': total_frames
                        }
                    else:
                        current_scene['labels'][label] = data
                
                # Update confidence
                current_scene['scene_confidence'] = max(current_scene.get('scene_confidence', 0), scene.get('scene_confidence', 0))
                
            else:
                # Start new scene
                if current_scene:
                    final_scenes.append(current_scene)
                
                current_scene = {
                    'scene_id': len(final_scenes) + 1,
                    'start_time': scene['start_time'],
                    'end_time': scene['end_time'],
                    'duration': scene['duration'],
                    'scene_type': scene_type,
                    'scene_category': scene_category,
                    'primary_label': scene.get('primary_label', 'unknown'),
                    'scene_confidence': scene.get('scene_confidence', 0.5),
                    'labels': dict(scene['labels'])  # Copy labels
                }
        
        # Add the last scene
        if current_scene:
            final_scenes.append(current_scene)
        
        return final_scenes
    
    def _store_video_scene_classification_new(self, user_id: str, project_id: str, video_uri: str, 
                                            final_scenes: List[Dict[str, Any]], raw_results: Dict[str, Any]) -> bool:
        """
        Store video scene classification using the new consistent storage pattern.
        Follows the same pattern as image classification for architectural consistency.
        
        Returns:
            bool: True if storage successful, False otherwise
        """
        try:
            # Create video scene data following the new pattern
            video_scenes_data = {
                "video_uri": video_uri,
                "video_duration": raw_results["video_duration"],
                "total_scenes": len(final_scenes),
                "scenes": final_scenes,
                "processing_metadata": {
                    "api_model": "builtin/stable",
                    "processing_time": raw_results.get("processing_time", 0),
                    "enhanced_detection": True,
                    "room_priority_system": True,
                    "total_frame_labels": len(raw_results.get("frame_labels", [])),
                    "total_segment_labels": len(raw_results.get("segment_labels", []))
                },
                "processed_at": datetime.utcnow().isoformat()
            }
            
            # Store using the new storage manager
            success = VideoScenesStorage.store_video_scenes(
                user_id=user_id,
                project_id=project_id,
                video_uri=video_uri,
                video_scenes_data=video_scenes_data
            )
            
            if success:
                logger.info(f"[ENHANCED_VIDEO_CLASSIFIER] Stored scene classification for {video_uri} with {len(final_scenes)} scenes using new storage pattern")
            else:
                logger.error(f"[ENHANCED_VIDEO_CLASSIFIER] Failed to store scene classification for {video_uri}")
            
            return success
            
        except Exception as e:
            logger.error(f"[ENHANCED_VIDEO_CLASSIFIER] Failed to store video scene classification: {e}")
            # Don't raise - classification can continue even if storage fails
            return False
    

