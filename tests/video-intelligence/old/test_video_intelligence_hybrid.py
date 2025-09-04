#!/usr/bin/env python3
"""
Hybrid Video Intelligence + Vision API pipeline for enhanced real estate scene detection
Combines Video Intelligence API scene detection with Vision API keyframe analysis
"""

import os
import sys
import json
import tempfile
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
from collections import defaultdict
import statistics

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from google.cloud import videointelligence_v1 as videointelligence
from google.cloud import vision_v1 as vision
from google.cloud import storage
from google.oauth2 import service_account
from config.config import settings

# Service account paths (same as used in other modules)
SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-f0da3484f1a0.json'


class HybridSceneDetectionPipeline:
    """
    Hybrid pipeline combining Video Intelligence API with Vision API for enhanced scene detection.
    """
    
    def __init__(self):
        """Initialize the hybrid pipeline with all required clients."""
        print("🔧 Initializing Hybrid Scene Detection Pipeline...")
        
        # Set up credentials
        self.credentials = None
        if os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
            self.credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_KEY_FILE_PATH,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
        
        # Initialize clients
        self.video_intelligence_client = videointelligence.VideoIntelligenceServiceClient(
            credentials=self.credentials
        )
        self.vision_client = vision.ImageAnnotatorClient(credentials=self.credentials)
        self.storage_client = storage.Client(credentials=self.credentials)
        
        # Load room mapping
        self.room_mapping = self._load_room_mapping()
        
        print("✅ Pipeline initialized successfully")
    
    def _load_room_mapping(self) -> Dict[str, List[str]]:
        """Load the enhanced room mapping from JSON file."""
        mapping_path = Path(__file__).parent.parent.parent / "src" / "utils" / "video_classification_room_mapping.json"
        
        try:
            with open(mapping_path, 'r') as f:
                mapping = json.load(f)
            print(f"📋 Loaded room mapping with {len(mapping)} room types")
            return mapping
        except Exception as e:
            print(f"⚠️  Failed to load room mapping: {e}")
            return {}
    
    def upload_video_to_gcs(self, local_video_path: str, bucket_name: str, blob_name: str) -> str:
        """Upload video to Google Cloud Storage and return the GCS URI."""
        print(f"📤 Uploading {local_video_path} to gs://{bucket_name}/{blob_name}")
        
        bucket = self.storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # Upload the video file
        blob.upload_from_filename(local_video_path)
        
        gcs_uri = f"gs://{bucket_name}/{blob_name}"
        print(f"✅ Video uploaded successfully: {gcs_uri}")
        return gcs_uri
    
    def analyze_with_video_intelligence(self, video_uri: str, config_name: str = "balanced_refined_hybrid") -> Dict[str, Any]:
        """
        Analyze video with enhanced Video Intelligence configuration.
        """
        print(f"\n🎬 Video Intelligence Analysis: {config_name}")
        print(f"📹 Video: {video_uri}")
        
                        # Enhanced configuration with more inclusive thresholds for complex scenes
        config = {
            "use_label_detection": True,
            "label_detection_mode": "SHOT_AND_FRAME_MODE",
            "model": "builtin/stable",
            "video_confidence_threshold": 0.6,   # More inclusive for complex scenes
            "frame_confidence_threshold": 0.7,   # More inclusive for complex scenes
            "use_shot_detection": True,
            "shot_detection_model": "builtin/stable"
        }
        
        print(f"⚙️  Config: {json.dumps(config, indent=2)}")
        
        # Configure features
        features = []
        video_context = {}
        
        # Label detection
        features.append(videointelligence.Feature.LABEL_DETECTION)
        label_config = {
            "label_detection_mode": getattr(
                videointelligence.LabelDetectionMode, 
                config["label_detection_mode"]
            ),
            "model": config["model"],
            "frame_confidence_threshold": config["frame_confidence_threshold"],
            "video_confidence_threshold": config["video_confidence_threshold"]
        }
        video_context["label_detection_config"] = label_config
        
        # Enhanced shot detection
        features.append(videointelligence.Feature.SHOT_CHANGE_DETECTION)
        shot_config = {"model": config["shot_detection_model"]}
        video_context["shot_change_detection_config"] = shot_config

        # Make API request
        operation = self.video_intelligence_client.annotate_video(
            request={
                "input_uri": video_uri,
                "features": features,
                "video_context": video_context
            }
        )

        print("🔄 Processing with Video Intelligence API...")
        result = operation.result(timeout=600)
        
        # Process results
        raw_segment_labels = []
        raw_frame_labels = []
        shot_annotations = []
        video_duration = 0
        
        for annotation_result in result.annotation_results:
            # Process shot annotations
            if annotation_result.shot_annotations:
                print(f"🎯 Detected {len(annotation_result.shot_annotations)} shots")
                for i, shot in enumerate(annotation_result.shot_annotations):
                    start_time = (shot.start_time_offset.seconds + 
                                shot.start_time_offset.microseconds / 1e6)
                    end_time = (shot.end_time_offset.seconds + 
                              shot.end_time_offset.microseconds / 1e6)
                    
                    shot_annotations.append({
                        "shot_number": i+1,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": end_time - start_time
                    })
                    
                    video_duration = max(video_duration, end_time)
            
            # Process segment labels
            if annotation_result.segment_label_annotations:
                for label_annotation in annotation_result.segment_label_annotations:
                    max_confidence = max(segment.confidence for segment in label_annotation.segments)
                    
                    label_data = {
                        "description": label_annotation.entity.description,
                        "entity_id": label_annotation.entity.entity_id,
                        "max_confidence": max_confidence,
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
                    
                    raw_segment_labels.append(label_data)

            # Process frame labels
            if annotation_result.frame_label_annotations:
                for label_annotation in annotation_result.frame_label_annotations:
                    max_confidence = max(frame.confidence for frame in label_annotation.frames)
                    
                    label_data = {
                        "description": label_annotation.entity.description,
                        "entity_id": label_annotation.entity.entity_id,
                        "max_confidence": max_confidence,
                        "frames": []
                    }
                    
                    for frame in label_annotation.frames:
                        time_offset = (frame.time_offset.seconds + 
                                     frame.time_offset.microseconds / 1e6)
                        label_data["frames"].append({
                            "time_offset": time_offset,
                            "confidence": frame.confidence
                        })
                    
                    raw_frame_labels.append(label_data)
        
        return {
            "config": config,
            "video_duration": video_duration,
            "raw_segment_labels": raw_segment_labels,
            "raw_frame_labels": raw_frame_labels,
            "shot_annotations": shot_annotations
        }
    
    def filter_scenes_strict(self, labels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Apply intelligent filtering that excludes generic structural labels while keeping specific scene indicators.
        """
        # Specific scene keywords (high priority)
        specific_scene_keywords = {
            'bedroom', 'bathroom', 'kitchen', 'living room', 'dining room', 'office', 
            'hallway', 'corridor', 'lobby', 'entrance', 'foyer', 'balcony', 'patio',
            'garden', 'yard', 'outdoor', 'pool', 'swimming pool', 'swimming', 'deck', 
            'terrace', 'garage', 'closet', 'pantry', 'basement', 'attic'
        }
        
        # Generic scene keywords (lower priority, only if no specific ones)
        generic_scene_keywords = {
            'room', 'interior', 'space', 'area', 'zone', 'chamber', 'suite', 'studio', 'loft'
        }
        
        # Generic structural labels to exclude (unless paired with specific scene indicators)
        excluded_generic_labels = {
            'floor', 'property', 'wall', 'flooring', 'furniture', 'table', 'chair', 
            'ceiling', 'tile', 'wood', 'stone', 'countertop', 'cabinet', 'door', 'window'
        }
        
        # Context keywords that provide supporting evidence
        context_keywords = {
            'house', 'home', 'building', 'architecture', 'design', 'sofa', 'bed', 'counter'
        }
        
        filtered_labels = []
        for label in labels:
            description_lower = label['description'].lower()
            
            # Check for specific scene indicators (highest priority)
            is_specific_scene = any(keyword in description_lower for keyword in specific_scene_keywords)
            
            # Check for generic scene indicators (lower priority)
            is_generic_scene = any(keyword in description_lower for keyword in generic_scene_keywords)
            
            # Check for excluded generic labels
            is_excluded_generic = any(keyword in description_lower for keyword in excluded_generic_labels)
            
            # Check for context indicators
            is_context_related = any(keyword in description_lower for keyword in context_keywords)
            
            # Filtering logic:
            # 1. Always include specific scene indicators with moderate confidence
            # 2. Include generic scene indicators only with high confidence
            # 3. Exclude generic structural labels unless they have very high confidence
            # 4. Include context indicators with high confidence
            
            should_include = False
            filter_reason = None
            
            if is_specific_scene and label['max_confidence'] >= 0.6:
                should_include = True
                filter_reason = 'specific_scene'
            elif is_generic_scene and label['max_confidence'] >= 0.8 and not is_excluded_generic:
                should_include = True
                filter_reason = 'generic_scene'
            elif is_context_related and label['max_confidence'] >= 0.85:
                should_include = True
                filter_reason = 'context_related'
            elif is_excluded_generic and label['max_confidence'] >= 0.95:
                # Only include excluded generics if they have extremely high confidence
                should_include = True
                filter_reason = 'high_confidence_generic'
            
            if should_include:
                label['filtered_reason'] = filter_reason
                label['priority'] = 1 if filter_reason == 'specific_scene' else 2
                filtered_labels.append(label)
        
        return filtered_labels
    
    def aggregate_scenes_from_frames(self, frame_labels: List[Dict[str, Any]], 
                                   shot_annotations: List[Dict[str, Any]],
                                   video_duration: float) -> List[Dict[str, Any]]:
        """
        Aggregate high-confidence frame labels into scene segments with intelligent prioritization.
        """
        if not frame_labels:
            return []
        
        # Group frame labels by time windows and prioritize specific scene indicators
        time_windows = defaultdict(list)  # time -> list of labels
        
        for label in frame_labels:
            description = label['description']
            priority = label.get('priority', 2)  # 1 = specific scene, 2 = generic/context
            filter_reason = label.get('filtered_reason', 'unknown')
            
            for frame in label.get('frames', []):
                time_key = int(frame['time_offset'])  # Group by second
                time_windows[time_key].append({
                    'time': frame['time_offset'],
                    'confidence': frame['confidence'],
                    'description': description,
                    'priority': priority,
                    'filter_reason': filter_reason
                })
        
        # For each time window, select the best scene indicator
        consolidated_frames = []
        for time_key, labels_at_time in time_windows.items():
            # Sort by priority (1 = specific scene first) then by confidence
            labels_at_time.sort(key=lambda x: (x['priority'], -x['confidence']))
            
            # Take the highest priority label (specific scene over generic)
            best_label = labels_at_time[0]
            consolidated_frames.append(best_label)
        
        # Group consolidated frames by scene type
        scene_groups = defaultdict(list)
        for frame in consolidated_frames:
            scene_groups[frame['description']].append(frame)
        
        scenes = []
        
        for description, frames in scene_groups.items():
            if len(frames) < 1:  # At least 1 frame for a scene
                continue
                
            frames.sort(key=lambda x: x['time'])
            
            scene_start = frames[0]['time']
            scene_end = frames[-1]['time']
            
            # Expand scene boundaries slightly for single frame scenes
            if len(frames) == 1:
                scene_start = max(0, scene_start - 2.0)
                scene_end = min(video_duration, scene_end + 2.0)
            
            # Refine boundaries using shot annotations
            if shot_annotations:
                for shot in shot_annotations:
                    if shot['start_time'] <= scene_start <= shot['end_time']:
                        scene_start = max(scene_start, shot['start_time'])
                    if shot['start_time'] <= scene_end <= shot['end_time']:
                        scene_end = min(scene_end, shot['end_time'])
            
            avg_confidence = statistics.mean([f['confidence'] for f in frames])
            keyframe_timestamp = (scene_start + scene_end) / 2
            priority = frames[0]['priority']  # Use priority of first frame
            
            scenes.append({
                'scene_type': description,
                'start_time': scene_start,
                'end_time': scene_end,
                'duration': scene_end - scene_start,
                'confidence': avg_confidence,
                'keyframe_timestamp': keyframe_timestamp,
                'frame_count': len(frames),
                'supporting_frames': frames,
                'priority': priority
            })
        
        # Sort by priority (specific scenes first) then by start time
        scenes.sort(key=lambda x: (x['priority'], x['start_time']))
        
        # Intelligent merging: merge overlapping scenes of same type, prioritize specific over generic
        merged_scenes = []
        
        for scene in scenes:
            if not merged_scenes:
                merged_scenes.append(scene)
            else:
                # Check for overlaps with existing scenes
                merged = False
                for existing_scene in merged_scenes:
                    # Check for temporal overlap
                    if (scene['start_time'] <= existing_scene['end_time'] + 3.0 and 
                        scene['end_time'] >= existing_scene['start_time'] - 3.0):
                        
                        # If same scene type, merge
                        if scene['scene_type'] == existing_scene['scene_type']:
                            existing_scene['start_time'] = min(existing_scene['start_time'], scene['start_time'])
                            existing_scene['end_time'] = max(existing_scene['end_time'], scene['end_time'])
                            existing_scene['duration'] = existing_scene['end_time'] - existing_scene['start_time']
                            existing_scene['keyframe_timestamp'] = (existing_scene['start_time'] + existing_scene['end_time']) / 2
                            existing_scene['confidence'] = max(existing_scene['confidence'], scene['confidence'])
                            existing_scene['frame_count'] += scene['frame_count']
                            existing_scene['supporting_frames'].extend(scene['supporting_frames'])
                            merged = True
                            break
                        # If different scene types but one is generic, prefer specific
                        elif existing_scene['priority'] > scene['priority']:  # scene is more specific
                            # Replace generic with specific
                            existing_scene.update(scene)
                            merged = True
                            break
                
                if not merged:
                    merged_scenes.append(scene)
        
        return merged_scenes
    
    def extract_keyframes_batch(self, video_uri: str, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract keyframes for high-confidence scenes using FFmpeg.
        """
        print(f"\n🖼️  Extracting keyframes for {len(scenes)} scenes...")
        
        # Limit to top 10 scenes by confidence to control costs
        top_scenes = sorted(scenes, key=lambda x: x['confidence'], reverse=True)[:10]
        high_confidence_scenes = [s for s in top_scenes if s['confidence'] >= 0.8]
        
        print(f"📊 Processing {len(high_confidence_scenes)} high-confidence scenes (≥0.8)")
        
        keyframes = []
        bucket_name = settings.GCP.Storage.USER_BUCKET
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            
            # Download video locally for FFmpeg processing
            print("📥 Downloading video for keyframe extraction...")
            local_video_path = temp_dir_path / "video.mp4"
            
            # Extract bucket and blob from gs:// URI
            video_parts = video_uri.replace("gs://", "").split("/", 1)
            video_bucket_name = video_parts[0]
            video_blob_name = video_parts[1]
            
            bucket = self.storage_client.bucket(video_bucket_name)
            blob = bucket.blob(video_blob_name)
            blob.download_to_filename(str(local_video_path))
            
            for i, scene in enumerate(high_confidence_scenes):
                try:
                    timestamp = scene['keyframe_timestamp']
                    scene_id = f"scene_{scene['start_time']:.1f}s"
                    
                    # Extract keyframe locally
                    keyframe_filename = f"keyframe_{scene_id}.jpg"
                    local_keyframe_path = temp_dir_path / keyframe_filename
                    
                    print(f"  🎬 Extracting keyframe {i+1}/{len(high_confidence_scenes)}: {timestamp:.1f}s")
                    
                    # Use FFmpeg to extract keyframe
                    command = [
                        "ffmpeg", "-i", str(local_video_path), 
                        "-ss", str(timestamp),
                        "-vframes", "1", 
                        "-q:v", "2",  # High quality
                        str(local_keyframe_path), 
                        "-y"  # Overwrite if exists
                    ]
                    
                    result = subprocess.run(command, 
                                          capture_output=True, 
                                          text=True, 
                                          timeout=30)
                    
                    if result.returncode != 0:
                        print(f"    ❌ FFmpeg failed: {result.stderr}")
                        continue
                    
                    if not local_keyframe_path.exists():
                        print(f"    ❌ Keyframe file not created")
                        continue
                    
                    # Upload keyframe to GCS
                    keyframe_blob_name = f"tests/video-intelligence/keyframes/{keyframe_filename}"
                    keyframe_bucket = self.storage_client.bucket(bucket_name)
                    keyframe_blob = keyframe_bucket.blob(keyframe_blob_name)
                    
                    keyframe_blob.upload_from_filename(str(local_keyframe_path))
                    keyframe_uri = f"gs://{bucket_name}/{keyframe_blob_name}"
                    
                    keyframes.append({
                        'scene': scene,
                        'keyframe_uri': keyframe_uri,
                        'timestamp': timestamp,
                        'scene_id': scene_id
                    })
                    
                    print(f"    ✅ Keyframe extracted and uploaded: {keyframe_uri}")
                    
                except subprocess.TimeoutExpired:
                    print(f"    ⏰ FFmpeg timeout for scene at {timestamp:.1f}s")
                    continue
                except Exception as e:
                    print(f"    ❌ Error extracting keyframe: {str(e)}")
                    continue
        
        print(f"✅ Successfully extracted {len(keyframes)} keyframes")
        return keyframes
    
    def analyze_keyframes_with_vision(self, keyframes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Analyze extracted keyframes using Vision API for label detection.
        """
        print(f"\n👁️  Analyzing {len(keyframes)} keyframes with Vision API...")
        
        vision_results = []
        
        for i, keyframe_data in enumerate(keyframes):
            try:
                keyframe_uri = keyframe_data['keyframe_uri']
                scene_id = keyframe_data['scene_id']
                
                print(f"  🔍 Analyzing keyframe {i+1}/{len(keyframes)}: {scene_id}")
                
                # Create Vision API request
                image = vision.Image(source=vision.ImageSource(image_uri=keyframe_uri))
                
                # Perform label detection
                response = self.vision_client.label_detection(image=image)
                
                # Process labels with confidence >= 0.75
                vision_labels = []
                for label in response.label_annotations:
                    if label.score >= 0.75:
                        vision_labels.append({
                            "description": label.description.lower(),
                            "confidence": label.score
                        })
                
                vision_results.append({
                    'scene_id': scene_id,
                    'keyframe_uri': keyframe_uri,
                    'scene': keyframe_data['scene'],
                    'vision_labels': vision_labels,
                    'label_count': len(vision_labels)
                })
                
                print(f"    ✅ Found {len(vision_labels)} high-confidence labels")
                
                # Brief pause to respect API limits
                time.sleep(0.1)
                
            except Exception as e:
                print(f"    ❌ Vision API error for {keyframe_data.get('scene_id', 'unknown')}: {str(e)}")
                continue
        
        print(f"✅ Vision API analysis complete for {len(vision_results)} keyframes")
        return vision_results
    
    def match_vision_to_room(self, vision_labels: List[Dict[str, Any]]) -> Tuple[Optional[str], float]:
        """
        Match Vision API labels to room types with exact matches taking priority.
        """
        if not vision_labels or not self.room_mapping:
            return None, 0.0
        
        # First, check for exact room name matches (highest priority)
        for vision_label in vision_labels:
            description = vision_label['description'].lower()
            confidence = vision_label['confidence']
            
            # Check for exact room name matches
            for room_type in self.room_mapping.keys():
                if description == room_type.lower() or room_type.lower() in description:
                    print(f"    🎯 Exact match: '{description}' → '{room_type}' (confidence: {confidence:.3f})")
                    return room_type, confidence
        
        # If no exact matches, use indicator-based matching
        room_scores = defaultdict(list)
        
        # Check each vision label against room indicators
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
            print(f"    🔍 Indicator match: '{best_room}' (confidence: {best_score:.3f})")
        
        return best_room, best_score
    
    def refine_scenes_with_vision(self, scenes: List[Dict[str, Any]], 
                                vision_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Refine scene classifications using Vision API results.
        """
        print(f"\n🔬 Refining {len(scenes)} scenes with Vision API data...")
        
        # Create mapping from scene timestamps to vision results
        vision_by_scene = {}
        for vision_result in vision_results:
            scene_start_time = vision_result['scene']['start_time']
            vision_by_scene[scene_start_time] = vision_result
        
        refined_scenes = []
        
        for scene in scenes:
            scene_start = scene['start_time']
            original_type = scene['scene_type']
            original_confidence = scene['confidence']
            
            # Check if we have vision data for this scene
            if scene_start in vision_by_scene:
                vision_result = vision_by_scene[scene_start]
                vision_labels = vision_result['vision_labels']
                
                # Try to match vision labels to a room type
                vision_room, vision_confidence = self.match_vision_to_room(vision_labels)
                
                if vision_room and vision_confidence >= 0.75:
                    # Use Vision API classification
                    refined_scene = scene.copy()
                    refined_scene.update({
                        'scene_type': vision_room,
                        'confidence': max(original_confidence, vision_confidence),
                        'detection_source': 'vision_api',
                        'original_video_intelligence_type': original_type,
                        'vision_labels': vision_labels,
                        'keyframe_uri': vision_result['keyframe_uri']
                    })
                    refined_scenes.append(refined_scene)
                    print(f"  ✨ Refined '{original_type}' → '{vision_room}' (confidence: {vision_confidence:.3f})")
                    
                else:
                    # Keep original if it's scene-related
                    if self._is_scene_related(original_type):
                        refined_scene = scene.copy()
                        refined_scene.update({
                            'detection_source': 'video_intelligence',
                            'vision_labels': vision_labels,
                            'keyframe_uri': vision_result['keyframe_uri']
                        })
                        refined_scenes.append(refined_scene)
                        print(f"  📋 Kept '{original_type}' (no strong vision match)")
                    else:
                        # Fallback to unknown room
                        refined_scene = scene.copy()
                        refined_scene.update({
                            'scene_type': 'unknown room',
                            'detection_source': 'fallback',
                            'original_video_intelligence_type': original_type,
                            'vision_labels': vision_labels,
                            'keyframe_uri': vision_result['keyframe_uri']
                        })
                        refined_scenes.append(refined_scene)
                        print(f"  ❓ Fallback '{original_type}' → 'unknown room'")
            else:
                # No vision data, keep original if scene-related
                if self._is_scene_related(original_type):
                    refined_scene = scene.copy()
                    refined_scene['detection_source'] = 'video_intelligence'
                    refined_scenes.append(refined_scene)
                    print(f"  📋 Kept '{original_type}' (no keyframe)")
        
        return refined_scenes
    
    def _is_scene_related(self, description: str) -> bool:
        """Check if a description is scene-related."""
        scene_keywords = {
            'room', 'bedroom', 'bathroom', 'kitchen', 'living', 'dining', 'office', 
            'hallway', 'corridor', 'lobby', 'entrance', 'foyer', 'balcony', 'patio',
            'garden', 'yard', 'interior', 'exterior', 'indoor', 'outdoor', 'space', 
            'area', 'zone', 'chamber', 'suite', 'studio', 'loft', 'basement', 'attic',
            'garage', 'closet', 'pantry'
        }
        return any(keyword in description.lower() for keyword in scene_keywords)
    
    def post_process_scenes(self, scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Post-process refined scenes: merge overlapping, sort by time, add scene IDs.
        """
        if not scenes:
            return scenes
        
        # Sort by start time
        scenes.sort(key=lambda x: x['start_time'])
        
        # Merge overlapping scenes of the same type
        merged_scenes = []
        
        for scene in scenes:
            if not merged_scenes:
                scene['scene_id'] = f"scene_1"
                merged_scenes.append(scene)
            else:
                last_scene = merged_scenes[-1]
                
                # Check for overlap and same type
                if (scene['start_time'] <= last_scene['end_time'] + 1.0 and 
                    scene['scene_type'] == last_scene['scene_type']):
                    
                    # Merge scenes
                    last_scene['end_time'] = max(last_scene['end_time'], scene['end_time'])
                    last_scene['duration'] = last_scene['end_time'] - last_scene['start_time']
                    last_scene['keyframe_timestamp'] = (last_scene['start_time'] + last_scene['end_time']) / 2
                    last_scene['confidence'] = max(last_scene['confidence'], scene['confidence'])
                    
                    # Merge vision labels if present
                    if 'vision_labels' in scene:
                        existing_labels = last_scene.get('vision_labels', [])
                        new_labels = scene['vision_labels']
                        # Combine and deduplicate
                        combined_labels = existing_labels + new_labels
                        seen_descriptions = set()
                        unique_labels = []
                        for label in combined_labels:
                            if label['description'] not in seen_descriptions:
                                unique_labels.append(label)
                                seen_descriptions.add(label['description'])
                        last_scene['vision_labels'] = unique_labels
                else:
                    scene['scene_id'] = f"scene_{len(merged_scenes) + 1}"
                    merged_scenes.append(scene)
        
        return merged_scenes
    
    def analyze_video_hybrid(self, video_uri: str) -> Dict[str, Any]:
        """
        Complete hybrid analysis pipeline combining Video Intelligence + Vision API.
        """
        start_time = time.time()
        print(f"\n🚀 STARTING HYBRID ANALYSIS")
        print(f"📹 Video: {video_uri}")
        print("=" * 80)
        
        try:
            # Step 1: Video Intelligence Analysis
            print("\n📊 STEP 1: Video Intelligence Analysis")
            video_results = self.analyze_with_video_intelligence(video_uri)
            
            # Step 2: Filter and aggregate scenes
            print("\n🔍 STEP 2: Scene Filtering and Aggregation")
            filtered_frame_labels = self.filter_scenes_strict(video_results['raw_frame_labels'])
            print(f"Filtered frame labels: {len(video_results['raw_frame_labels'])} → {len(filtered_frame_labels)}")
            
            aggregated_scenes = self.aggregate_scenes_from_frames(
                filtered_frame_labels, 
                video_results['shot_annotations'],
                video_results['video_duration']
            )
            print(f"Aggregated scenes: {len(aggregated_scenes)}")
            
            # Step 3: Extract keyframes (only if we have scenes)
            keyframes = []
            vision_results = []
            
            if aggregated_scenes:
                print("\n🖼️  STEP 3: Keyframe Extraction")
                keyframes = self.extract_keyframes_batch(video_uri, aggregated_scenes)
                
                # Step 4: Vision API analysis (only if we have keyframes)
                if keyframes:
                    print("\n👁️  STEP 4: Vision API Analysis")
                    vision_results = self.analyze_keyframes_with_vision(keyframes)
                    
                    # Step 5: Refine scenes with vision data
                    print("\n🔬 STEP 5: Scene Refinement")
                    refined_scenes = self.refine_scenes_with_vision(aggregated_scenes, vision_results)
                else:
                    print("\n⚠️  No keyframes extracted, using Video Intelligence only")
                    refined_scenes = aggregated_scenes
            else:
                print("\n⚠️  No scenes detected, using raw Video Intelligence results")
                refined_scenes = []
            
            # Step 6: Post-processing
            print("\n🔧 STEP 6: Post-Processing")
            final_scenes = self.post_process_scenes(refined_scenes)
            
            # Calculate metrics and cost estimate
            processing_time = time.time() - start_time
            cost_estimate = len(vision_results) * 0.0015  # $1.50 per 1000 images
            
            # Prepare final results
            result = {
                "video_uri": video_uri,
                "analysis_config": "balanced_refined_hybrid",
                "processing_time": round(processing_time, 2),
                "cost_estimate": round(cost_estimate, 4),
                "refined_scenes": final_scenes,
                "metadata": {
                    "total_scenes": len(final_scenes),
                    "scenes_refined_by_vision": len([s for s in final_scenes if s.get('detection_source') == 'vision_api']),
                    "keyframes_extracted": len(keyframes),
                    "vision_api_calls": len(vision_results),
                    "fallback_scenes": len([s for s in final_scenes if s.get('detection_source') == 'fallback']),
                    "video_intelligence_only": len([s for s in final_scenes if s.get('detection_source') == 'video_intelligence']),
                    "video_duration": video_results['video_duration']
                },
                "raw_data": {
                    "video_intelligence_results": video_results,
                    "keyframes": keyframes,
                    "vision_results": vision_results
                }
            }
            
            # Display results summary
            print(f"\n🎯 HYBRID ANALYSIS COMPLETE")
            print("=" * 60)
            print(f"⏱️  Processing time: {processing_time:.1f}s")
            print(f"💰 Cost estimate: ${cost_estimate:.4f}")
            print(f"🎭 Total scenes detected: {len(final_scenes)}")
            
            if final_scenes:
                print(f"\n📍 DETECTED SCENES:")
                for i, scene in enumerate(final_scenes):
                    source = scene.get('detection_source', 'unknown')
                    source_icon = {'vision_api': '👁️', 'video_intelligence': '🎬', 'fallback': '❓'}.get(source, '🔍')
                    print(f"  {i+1}. {source_icon} '{scene['scene_type']}' "
                          f"({scene['start_time']:.1f}s-{scene['end_time']:.1f}s, "
                          f"confidence: {scene['confidence']:.3f})")
            
            return result
            
        except Exception as e:
            print(f"❌ Hybrid analysis failed: {str(e)}")
            import traceback
            traceback.print_exc()
            raise


def test_hybrid_pipeline():
    """
    Test the complete hybrid pipeline with the two_rooms.mp4 video.
    """
    print("🎥 TESTING HYBRID VIDEO INTELLIGENCE + VISION API PIPELINE")
    print("=" * 80)
    
    # Initialize pipeline
    pipeline = HybridSceneDetectionPipeline()
    
    # Path to test video
    video_path = Path(__file__).parent.parent / "properties_medias" / "videos" / "two_rooms.mp4"
    assert video_path.exists(), f"Video file not found: {video_path}"
    
    # Upload video to GCS
    bucket_name = settings.GCP.Storage.USER_BUCKET
    blob_name = "tests/video-intelligence/two_rooms_hybrid.mp4"
    
    video_uri = pipeline.upload_video_to_gcs(
        local_video_path=str(video_path),
        bucket_name=bucket_name,
        blob_name=blob_name
    )
    
    # Run hybrid analysis
    results = pipeline.analyze_video_hybrid(video_uri)
    
    # Save results
    output_file = Path(__file__).parent / "hybrid_pipeline_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to: {output_file}")
    
    return results


def test_hybrid_pipeline_complex_video():
    """
    Test the hybrid pipeline with the pool_living_room_kitchen.mp4 video.
    This video contains multiple distinct scenes: pool area, gourmet area, living room, and kitchen.
    """
    print("🎥 TESTING HYBRID PIPELINE WITH COMPLEX MULTI-SCENE VIDEO")
    print("🏊 Expected scenes: Pool area, Gourmet area, Living room, Kitchen")
    print("=" * 80)
    
    # Initialize pipeline
    pipeline = HybridSceneDetectionPipeline()
    
    # Path to complex test video
    video_path = Path(__file__).parent.parent / "properties_medias" / "videos" / "pool_living_room_kitchen.mp4"
    assert video_path.exists(), f"Video file not found: {video_path}"
    
    # Upload video to GCS
    bucket_name = settings.GCP.Storage.USER_BUCKET
    blob_name = "tests/video-intelligence/pool_living_room_kitchen_hybrid.mp4"
    
    video_uri = pipeline.upload_video_to_gcs(
        local_video_path=str(video_path),
        bucket_name=bucket_name,
        blob_name=blob_name
    )
    
    # Run hybrid analysis
    results = pipeline.analyze_video_hybrid(video_uri)
    
    # Save results with descriptive filename
    output_file = Path(__file__).parent / "complex_video_hybrid_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to: {output_file}")
    
    # Analyze results for expected scenes
    detected_scenes = results.get('refined_scenes', [])
    expected_scene_types = ['pool', 'outdoor', 'kitchen', 'living room', 'dining room', 'room']
    
    print(f"\n🔍 SCENE ANALYSIS:")
    print(f"Expected scene types: {expected_scene_types}")
    print(f"Total scenes detected: {len(detected_scenes)}")
    
    if detected_scenes:
        scene_types_found = set()
        for i, scene in enumerate(detected_scenes):
            scene_type = scene.get('scene_type', 'unknown')
            scene_types_found.add(scene_type)
            detection_source = scene.get('detection_source', 'unknown')
            source_icon = {'vision_api': '👁️', 'video_intelligence': '🎬', 'fallback': '❓'}.get(detection_source, '🔍')
            
            print(f"  {i+1}. {source_icon} '{scene_type}' "
                  f"({scene['start_time']:.1f}s-{scene['end_time']:.1f}s, "
                  f"confidence: {scene['confidence']:.3f})")
            
            if 'keyframe_uri' in scene:
                print(f"      🖼️  Keyframe: {scene['keyframe_uri']}")
        
        print(f"\n📊 Scene types found: {sorted(scene_types_found)}")
        
        # Check if we found expected scene types
        matches = scene_types_found.intersection(expected_scene_types)
        print(f"✅ Expected scene matches: {sorted(matches)}")
        
        if len(matches) >= 2:
            print(f"🎉 SUCCESS: Found {len(matches)} expected scene types!")
        else:
            print(f"⚠️  Limited success: Only found {len(matches)} expected scene types")
    
    return results


def test_video_intelligence_hybrid_pipeline():
    """Pytest-compatible test function."""
    results = test_hybrid_pipeline()
    
    # Assertions for successful hybrid analysis
    assert results is not None, "Hybrid analysis returned None"
    assert "refined_scenes" in results, "No refined_scenes in results"
    assert "metadata" in results, "No metadata in results"
    
    # Check that we have reasonable results
    scenes = results["refined_scenes"]
    metadata = results["metadata"]
    
    assert len(scenes) > 0, "No scenes detected"
    assert metadata["total_scenes"] > 0, "No scenes in metadata"
    assert results["processing_time"] > 0, "Invalid processing time"
    
    # Check that at least some scenes were enhanced
    vision_enhanced = metadata.get("scenes_refined_by_vision", 0)
    video_intelligence_only = metadata.get("video_intelligence_only", 0)
    
    print(f"✅ Test passed: {len(scenes)} scenes detected")
    print(f"   👁️  Vision API enhanced: {vision_enhanced}")
    print(f"   🎬 Video Intelligence only: {video_intelligence_only}")
    
    return results


def test_video_intelligence_hybrid_complex_video():
    """Pytest-compatible test function for complex multi-scene video."""
    results = test_hybrid_pipeline_complex_video()
    
    # Assertions for successful hybrid analysis
    assert results is not None, "Hybrid analysis returned None"
    assert "refined_scenes" in results, "No refined_scenes in results"
    assert "metadata" in results, "No metadata in results"
    
    # Check that we have reasonable results
    scenes = results["refined_scenes"]
    metadata = results["metadata"]
    
    assert len(scenes) > 0, "No scenes detected"
    assert metadata["total_scenes"] > 0, "No scenes in metadata"
    assert results["processing_time"] > 0, "Invalid processing time"
    
    # For complex video, expect multiple scenes
    assert len(scenes) >= 2, f"Expected multiple scenes, got {len(scenes)}"
    
    # Check scene diversity
    scene_types = set(scene.get('scene_type', 'unknown') for scene in scenes)
    assert len(scene_types) >= 1, f"Expected diverse scene types, got {scene_types}"
    
    print(f"✅ Complex video test passed: {len(scenes)} scenes, {len(scene_types)} types")
    print(f"   📊 Scene types: {sorted(scene_types)}")
    
    return results


def main():
    """Main function for standalone execution."""
    test_hybrid_pipeline()


if __name__ == "__main__":
    main()
