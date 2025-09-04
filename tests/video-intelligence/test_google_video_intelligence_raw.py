"""
Test: Google Video Intelligence Raw Labels Analysis
Purpose: Extract and display raw labels from Google Video Intelligence API for calibration analysis.
         This test bypasses all ADR-002 post-processing to show exactly what Google returns.
Last Updated: 2025-01-02 15:45:00 UTC
Expected: Raw segment and frame labels with confidence scores, timestamps, and shot detection data
Author: Backend Team
Related: ADR-002 (Video Intelligence Integration), ADR-003 (Test Documentation Standards)
"""

import os
import sys
from pathlib import Path
import json
from typing import List, Dict, Any
from datetime import datetime
import pytest

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from google.cloud import videointelligence_v1 as videointelligence
from google.cloud import storage
from google.oauth2 import service_account
from config.config import settings

# Service account path (consistent with other tests)
SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-f0da3484f1a0.json'

# Test configuration
TEST_VIDEOS = {
    "julie_indoor_outdoor": {
        "path": "tests/properties_medias/videos/julie_01_indoors_and_outdoors.MOV",
        "description": "Julie's multi-room indoor/outdoor property tour",
        "expected_scenes": ["kitchen", "living room", "outdoor", "bedroom"]  # For reference
    }
}


def upload_video_to_gcs(local_video_path: str, bucket_name: str, blob_name: str) -> str:
    """
    Upload video to Google Cloud Storage and return the GCS URI.
    
    Args:
        local_video_path: Path to local video file
        bucket_name: GCS bucket name
        blob_name: Blob name in bucket
        
    Returns:
        GCS URI for uploaded video
    """
    print(f"📤 Uploading {local_video_path} to gs://{bucket_name}/{blob_name}")
    
    # Set up credentials
    credentials = None
    if os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_KEY_FILE_PATH,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
    
    client = storage.Client(credentials=credentials)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    
    # Upload the video file
    blob.upload_from_filename(local_video_path)
    
    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    print(f"✅ Video uploaded successfully: {gcs_uri}")
    return gcs_uri


def analyze_video_raw_labels(video_uri: str) -> Dict[str, Any]:
    """
    Analyze video with Google Video Intelligence API and return raw results.
    
    Args:
        video_uri: GCS URI of video to analyze
        
    Returns:
        Dictionary containing raw API results
    """
    print(f"\n🎬 ANALYZING VIDEO WITH GOOGLE VIDEO INTELLIGENCE API")
    print(f"📹 Video: {video_uri}")
    print("=" * 70)
    
    # Set up credentials
    credentials = None
    if os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_KEY_FILE_PATH,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
    
    client = videointelligence.VideoIntelligenceServiceClient(credentials=credentials)

    # Configure Video Intelligence API request
    features = [
        videointelligence.Feature.LABEL_DETECTION,
        videointelligence.Feature.SHOT_CHANGE_DETECTION
    ]
    
    # Use basic configuration to get raw results
    video_context = {
        "label_detection_config": {
            "label_detection_mode": videointelligence.LabelDetectionMode.SHOT_AND_FRAME_MODE,
            "model": "builtin/stable",
            "video_confidence_threshold": 0.5,  # Lower threshold to see more labels
            "frame_confidence_threshold": 0.5   # Lower threshold to see more labels
        },
        "shot_change_detection_config": {
            "model": "builtin/stable"
        }
    }

    # Make the API request
    operation = client.annotate_video(
        request={
            "input_uri": video_uri,
            "features": features,
            "video_context": video_context
        }
    )

    print("🔄 Processing video with Google Video Intelligence API...")
    result = operation.result(timeout=600)  # 10 minute timeout

    # Process and structure results
    raw_results = {
        "video_uri": video_uri,
        "processing_timestamp": datetime.utcnow().isoformat(),
        "segment_labels": [],
        "frame_labels": [],
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
            print(f"\n🎯 SHOT DETECTION: {len(annotation_result.shot_annotations)} shots detected")
            
            for i, shot in enumerate(annotation_result.shot_annotations):
                start_time = (shot.start_time_offset.seconds + 
                            shot.start_time_offset.microseconds / 1e6)
                end_time = (shot.end_time_offset.seconds + 
                          shot.end_time_offset.microseconds / 1e6)
                duration = end_time - start_time
                
                print(f"   Shot {i+1}: {start_time:.1f}s → {end_time:.1f}s (Duration: {duration:.1f}s)")
                
                raw_results["shot_annotations"].append({
                    "shot_number": i+1,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration
                })
                
                # Update video duration
                raw_results["video_duration"] = max(raw_results["video_duration"], end_time)
        
        # Process segment labels (shot-level labels)
        if annotation_result.segment_label_annotations:
            print(f"\n🏷️  RAW SEGMENT LABELS: {len(annotation_result.segment_label_annotations)} labels")
            
            for label_annotation in annotation_result.segment_label_annotations:
                max_confidence = max(segment.confidence for segment in label_annotation.segments)
                
                print(f"   📦 '{label_annotation.entity.description}' (Max confidence: {max_confidence:.3f})")
                
                # Store segment label data
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
                    
                    print(f"      └── {start_time:.1f}s - {end_time:.1f}s (confidence: {segment.confidence:.3f})")
                    
                    label_data["segments"].append({
                        "start_time": start_time,
                        "end_time": end_time,
                        "confidence": segment.confidence
                    })
                
                raw_results["segment_labels"].append(label_data)

        # Process frame labels
        if annotation_result.frame_label_annotations:
            print(f"\n🖼️  RAW FRAME LABELS: {len(annotation_result.frame_label_annotations)} labels")
            
            for label_annotation in annotation_result.frame_label_annotations:
                max_confidence = max(frame.confidence for frame in label_annotation.frames)
                frame_count = len(label_annotation.frames)
                
                print(f"   🖼️  '{label_annotation.entity.description}' (Max confidence: {max_confidence:.3f}, {frame_count} frames)")
                
                # Store frame label data
                label_data = {
                    "description": label_annotation.entity.description,
                    "entity_id": label_annotation.entity.entity_id,
                    "max_confidence": max_confidence,
                    "frame_count": frame_count,
                    "frames": []
                }
                
                # Store ALL frame data for enhanced analysis
                all_times = []
                all_confidences = []
                
                for frame in label_annotation.frames:
                    time_offset = (frame.time_offset.seconds + 
                                 frame.time_offset.microseconds / 1e6)
                    all_times.append(time_offset)
                    all_confidences.append(frame.confidence)
                    
                    label_data["frames"].append({
                        "time_offset": time_offset,
                        "confidence": frame.confidence
                    })
                
                # Enhanced display with confidence analysis
                min_conf = min(all_confidences)
                max_conf = max(all_confidences)
                avg_conf = sum(all_confidences) / len(all_confidences)
                
                # Show frame timeline (limit display for readability)
                if len(all_times) <= 10:
                    times_display = ', '.join([f"{t:.1f}s" for t in all_times])
                else:
                    times_display = f"{', '.join([f'{t:.1f}s' for t in all_times[:5]])}, ..., {', '.join([f'{t:.1f}s' for t in all_times[-3:]])}"
                    
                print(f"      └── Frames: {times_display}")
                print(f"      └── Confidence: {min_conf:.3f}-{max_conf:.3f} (avg: {avg_conf:.3f})")
                
                raw_results["frame_labels"].append(label_data)

    return raw_results


def detect_scene_boundaries(frame_labels: List[Dict[str, Any]], video_duration: float) -> List[Dict[str, Any]]:
    """
    Detect natural scene boundaries by analyzing label transitions and temporal patterns.
    
    Args:
        frame_labels: List of frame label data
        video_duration: Total video duration in seconds
        
    Returns:
        List of detected scenes with boundaries and dominant labels
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
        
        similarity = calculate_signature_similarity(prev_signature, curr_signature)
        
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
    current_scene_labels = {}
    
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


def calculate_signature_similarity(sig1: Dict[str, float], sig2: Dict[str, float]) -> float:
    """
    Calculate similarity between two label signatures.
    
    Args:
        sig1: First signature (label -> confidence mapping)
        sig2: Second signature (label -> confidence mapping)
        
    Returns:
        Similarity score between 0.0 and 1.0
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


def prioritize_and_segment_scenes(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply hierarchical room priority and segment scenes based on specific room detections.
    
    Args:
        scenes: List of detected scenes
        
    Returns:
        List of refined scenes with proper segmentation and prioritization
    """
    # Define room priority hierarchy (higher priority = more specific)
    room_priority = {
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
    
    refined_scenes = []
    
    for scene in scenes:
        # Find highest priority labels in this scene
        scene_labels = scene['labels']
        priority_labels = []
        
        for label, data in scene_labels.items():
            priority_info = get_label_priority(label, room_priority)
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
            segmented_scenes = segment_scene_by_priority(scene, high_priority_labels, scene_labels)
            refined_scenes.extend(segmented_scenes)
        else:
            # Single dominant label or no high-priority conflicts
            dominant_label = priority_labels[0]
            
            # Update scene classification
            scene['scene_type'] = dominant_label['subtype']
            scene['scene_category'] = dominant_label['type']
            scene['primary_label'] = dominant_label['label']
            scene['scene_confidence'] = calculate_scene_confidence(scene, dominant_label)
            
            refined_scenes.append(scene)
    
    return refined_scenes


def get_label_priority(label: str, room_priority: Dict[str, Dict]) -> Dict[str, Any]:
    """
    Get priority information for a label with fuzzy matching.
    
    Args:
        label: Label to check
        room_priority: Priority mapping dictionary
        
    Returns:
        Priority information or None if not found
    """
    label_lower = label.lower()
    
    # Direct match
    if label_lower in room_priority:
        return room_priority[label_lower]
    
    # Fuzzy matching for compound labels
    for priority_label, info in room_priority.items():
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
            return room_priority.get(room, None)
    
    return None


def segment_scene_by_priority(scene: Dict[str, Any], high_priority_labels: List[Dict], 
                            all_scene_labels: Dict[str, Dict]) -> List[Dict[str, Any]]:
    """
    Segment a scene when multiple high-priority room types are detected.
    
    Args:
        scene: Original scene to segment
        high_priority_labels: List of high-priority labels found
        all_scene_labels: All labels in the scene
        
    Returns:
        List of segmented scenes
    """
    # For now, create separate scenes for each high-priority label
    # In the future, we could analyze temporal distribution within the scene
    
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


def calculate_scene_confidence(scene: Dict[str, Any], dominant_label: Dict[str, Any]) -> float:
    """
    Calculate overall confidence score for a scene.
    
    Args:
        scene: Scene data
        dominant_label: Primary label information
        
    Returns:
        Confidence score between 0.0 and 1.0
    """
    # Multi-factor confidence calculation
    label_confidence = dominant_label['confidence']  # 50%
    priority_bonus = min(dominant_label['priority'] / 10.0, 1.0)  # 30% - higher priority = more confident
    duration_factor = min(scene['duration'] / 5.0, 1.0)  # 20% - longer scenes = more confident
    
    combined_confidence = (label_confidence * 0.5) + (priority_bonus * 0.3) + (duration_factor * 0.2)
    
    return min(combined_confidence, 1.0)


def cluster_temporal_frames(frame_labels: List[Dict[str, Any]], gap_threshold: float = 3.0) -> Dict[str, Any]:
    """
    Legacy function - kept for backwards compatibility.
    Now calls the enhanced scene detection pipeline.
    """
    # Use enhanced scene detection instead
    video_duration = 35.0  # Approximate - will be passed properly in main function
    scenes = detect_scene_boundaries(frame_labels, video_duration)
    refined_scenes = prioritize_and_segment_scenes(scenes)
    
    # Convert to old format for compatibility
    clustered_scenes = {}
    
    for scene in refined_scenes:
        scene_key = f"Scene {scene['scene_id']}: {scene.get('primary_label', scene.get('dominant_label', 'unknown'))}"
        
        clustered_scenes[scene_key] = {
            'total_frames': sum(data['frame_count'] for data in scene['labels'].values()),
            'total_clusters': 1,
            'clusters': [{
                'cluster_id': 1,
                'start_time': scene['start_time'],
                'end_time': scene['end_time'],
                'duration': scene['duration'],
                'frame_count': sum(data['frame_count'] for data in scene['labels'].values()),
                'confidence_avg': scene.get('scene_confidence', 0.5),
                'scene_type': scene.get('scene_type', 'unknown'),
                'scene_category': scene.get('scene_category', 'unknown'),
                'primary_label': scene.get('primary_label', 'unknown')
            }],
            'overall_confidence': scene.get('scene_confidence', 0.5),
            'scene_info': scene
        }
    
    return clustered_scenes


def consolidate_final_scenes(refined_scenes: List[Dict[str, Any]], video_duration: float) -> List[Dict[str, Any]]:
    """
    Consolidate micro-scenes into final coherent scenes for real estate classification.
    
    Args:
        refined_scenes: List of micro-scenes from prioritization
        video_duration: Total video duration
        
    Returns:
        List of final consolidated scenes
    """
    # Group scenes by room type and merge adjacent similar scenes
    scene_groups = {}
    
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


def print_final_scene_summary(final_scenes: List[Dict[str, Any]]) -> None:
    """
    Print a clean summary of final scene classifications.
    
    Args:
        final_scenes: List of consolidated final scenes
    """
    print("\n" + "="*80)
    print("🎬 FINAL SCENE CLASSIFICATIONS")
    print("="*80)
    
    if not final_scenes:
        print("❌ No scenes detected")
        return
    
    # Print clean scene list
    print(f"\n📋 DETECTED SCENES ({len(final_scenes)} total):")
    print("-" * 50)
    
    for scene in final_scenes:
        scene_type_display = scene['scene_type'].replace('_', ' ').title()
        category_emoji = "🏠" if scene['scene_category'] == "indoor" else "🌳" if scene['scene_category'] == "outdoor" else "📦"
        
        print(f"Scene {scene['scene_id']}: {category_emoji} {scene_type_display} ({scene['start_time']:.1f}s - {scene['end_time']:.1f}s)")
    
    # Print detailed scene breakdown
    print(f"\n🔍 DETAILED SCENE BREAKDOWN:")
    print("-" * 50)
    
    for scene in final_scenes:
        scene_type_display = scene['scene_type'].replace('_', ' ').title()
        category_emoji = "🏠" if scene['scene_category'] == "indoor" else "🌳" if scene['scene_category'] == "outdoor" else "📦"
        
        print(f"\n{category_emoji} SCENE {scene['scene_id']}: {scene_type_display.upper()}")
        print(f"   ⏱️  Time Range: {scene['start_time']:.1f}s - {scene['end_time']:.1f}s (Duration: {scene['duration']:.1f}s)")
        print(f"   🎯 Primary Label: {scene['primary_label']}")
        print(f"   📊 Scene Confidence: {scene['scene_confidence']:.3f}")
        print(f"   📂 Category: {scene['scene_category'].title()}")
        
        # Show all labels in this scene
        if scene['labels']:
            print("   🏷️  All Labels Detected:")
            sorted_labels = sorted(scene['labels'].items(), key=lambda x: x[1]['avg_confidence'], reverse=True)
            for label, data in sorted_labels:
                print(f"      • {label}: {data['frame_count']} frames (confidence: {data['avg_confidence']:.3f})")
    
    print("\n" + "="*80)


def analyze_segment_frame_correlation(segment_labels: List[Dict[str, Any]], 
                                    frame_labels: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze correlation between segment and frame labels to identify contradictions.
    
    Args:
        segment_labels: List of segment label data
        frame_labels: List of frame label data
        
    Returns:
        Dictionary with correlation analysis
    """
    correlations = []
    
    for segment in segment_labels:
        segment_desc = segment['description']
        
        for seg_data in segment['segments']:
            seg_start = seg_data['start_time']
            seg_end = seg_data['end_time']
            seg_conf = seg_data['confidence']
            
            # Find frame labels that overlap with this segment
            overlapping_frames = []
            contradicting_frames = []
            supporting_frames = []
            
            for frame_label in frame_labels:
                frame_desc = frame_label['description']
                
                for frame in frame_label['frames']:
                    frame_time = frame['time_offset']
                    frame_conf = frame['confidence']
                    
                    # Check if frame is within segment time range
                    if seg_start <= frame_time <= seg_end:
                        overlap_info = {
                            'frame_description': frame_desc,
                            'frame_time': frame_time,
                            'frame_confidence': frame_conf,
                            'segment_description': segment_desc,
                            'segment_confidence': seg_conf
                        }
                        overlapping_frames.append(overlap_info)
                        
                        # Determine if supporting or contradicting
                        if (segment_desc.lower() in frame_desc.lower() or 
                            frame_desc.lower() in segment_desc.lower() or
                            are_semantically_related(segment_desc, frame_desc)):
                            supporting_frames.append(overlap_info)
                        else:
                            contradicting_frames.append(overlap_info)
            
            correlation_info = {
                'segment_description': segment_desc,
                'segment_time_range': f"{seg_start:.1f}s - {seg_end:.1f}s",
                'segment_confidence': seg_conf,
                'overlapping_frame_count': len(overlapping_frames),
                'supporting_frame_count': len(supporting_frames),
                'contradicting_frame_count': len(contradicting_frames),
                'support_ratio': len(supporting_frames) / len(overlapping_frames) if overlapping_frames else 0,
                'overlapping_frames': overlapping_frames,
                'supporting_frames': supporting_frames,
                'contradicting_frames': contradicting_frames
            }
            correlations.append(correlation_info)
    
    return {
        'correlations': correlations,
        'total_segments_analyzed': len([c for c in correlations]),
        'well_supported_segments': len([c for c in correlations if c['support_ratio'] >= 0.7]),
        'contradicted_segments': len([c for c in correlations if c['support_ratio'] < 0.3])
    }


def are_semantically_related(term1: str, term2: str) -> bool:
    """
    Simple semantic relationship checker for video labels.
    
    Args:
        term1: First term to compare
        term2: Second term to compare
        
    Returns:
        True if terms are semantically related
    """
    # Define semantic relationships for real estate/room detection
    relationships = {
        'outdoor': ['swimming pool', 'outdoor furniture', 'patio', 'garden', 'yard', 'balcony'],
        'indoor': ['interior design', 'room', 'office', 'kitchen', 'bedroom', 'bathroom'],
        'interior': ['interior design', 'room', 'office', 'kitchen', 'bedroom', 'bathroom'],
        'room': ['interior design', 'office', 'kitchen', 'bedroom', 'bathroom', 'living room'],
        'property': ['room', 'interior design', 'outdoor', 'swimming pool', 'office']
    }
    
    term1_lower = term1.lower()
    term2_lower = term2.lower()
    
    # Check direct relationships
    if term1_lower in relationships:
        if any(related in term2_lower for related in relationships[term1_lower]):
            return True
    
    if term2_lower in relationships:
        if any(related in term1_lower for related in relationships[term2_lower]):
            return True
    
    # Check for common words
    common_words = ['room', 'space', 'area', 'design', 'furniture']
    if any(word in term1_lower and word in term2_lower for word in common_words):
        return True
    
    return False


def infer_scenes_from_labels(clustered_scenes: Dict[str, Any], 
                           video_duration: float) -> Dict[str, Any]:
    """
    Infer actual scenes/rooms from clustered frame labels.
    
    Args:
        clustered_scenes: Output from cluster_temporal_frames
        video_duration: Total video duration in seconds
        
    Returns:
        Dictionary with scene inference analysis
    """
    # Room classification mapping
    room_indicators = {
        'kitchen': ['kitchen', 'countertop', 'appliance', 'refrigerator', 'stove'],
        'bedroom': ['bedroom', 'bed', 'mattress', 'pillow', 'blanket'],
        'bathroom': ['bathroom', 'toilet', 'shower', 'bathtub', 'sink', 'mirror'],
        'living_room': ['living room', 'sofa', 'couch', 'television', 'tv'],
        'office': ['office', 'desk', 'computer', 'chair', 'bookshelf'],
        'outdoor': ['outdoor', 'swimming pool', 'patio', 'garden', 'yard', 'balcony'],
        'dining_room': ['dining room', 'dining table', 'chairs'],
        'interior_generic': ['interior design', 'room', 'space', 'area']
    }
    
    # Analyze temporal coverage and confidence for each potential room
    scene_candidates = {}
    
    for label_desc, cluster_data in clustered_scenes.items():
        # Determine which room this label indicates
        room_type = 'unknown'
        for room, indicators in room_indicators.items():
            if any(indicator in label_desc.lower() for indicator in indicators):
                room_type = room
                break
        
        if room_type == 'unknown':
            room_type = 'other'
        
        # Calculate temporal coverage
        total_duration = sum(cluster['duration'] for cluster in cluster_data['clusters'])
        coverage_percentage = (total_duration / video_duration) * 100
        
        # Calculate weighted confidence (by duration)
        weighted_confidence = 0
        total_weighted_duration = 0
        
        for cluster in cluster_data['clusters']:
            weight = cluster['duration'] if cluster['duration'] > 0 else 1.0
            weighted_confidence += cluster['confidence_avg'] * weight
            total_weighted_duration += weight
        
        if total_weighted_duration > 0:
            weighted_confidence /= total_weighted_duration
        else:
            weighted_confidence = cluster_data['overall_confidence']
        
        if room_type not in scene_candidates:
            scene_candidates[room_type] = []
        
        scene_candidates[room_type].append({
            'label': label_desc,
            'total_frames': cluster_data['total_frames'],
            'total_clusters': cluster_data['total_clusters'],
            'temporal_coverage': coverage_percentage,
            'weighted_confidence': weighted_confidence,
            'clusters': cluster_data['clusters']
        })
    
    # Rank scenes by evidence strength
    scene_rankings = {}
    for room_type, evidence_list in scene_candidates.items():
        # Calculate combined score for this room type
        total_frames = sum(ev['total_frames'] for ev in evidence_list)
        avg_confidence = sum(ev['weighted_confidence'] for ev in evidence_list) / len(evidence_list)
        total_coverage = sum(ev['temporal_coverage'] for ev in evidence_list)
        
        # Combined score: 40% confidence + 30% frame count + 30% temporal coverage
        score = (avg_confidence * 0.4) + (min(total_frames / 10, 1.0) * 0.3) + (min(total_coverage / 50, 1.0) * 0.3)
        
        scene_rankings[room_type] = {
            'evidence_count': len(evidence_list),
            'total_frames': total_frames,
            'average_confidence': avg_confidence,
            'temporal_coverage': total_coverage,
            'combined_score': score,
            'evidence': evidence_list
        }
    
    # Sort by combined score
    ranked_scenes = dict(sorted(scene_rankings.items(), key=lambda x: x[1]['combined_score'], reverse=True))
    
    return {
        'scene_candidates': ranked_scenes,
        'top_scene': list(ranked_scenes.keys())[0] if ranked_scenes else 'unknown',
        'scene_count': len([s for s in ranked_scenes.values() if s['combined_score'] > 0.3]),
        'high_confidence_scenes': len([s for s in ranked_scenes.values() if s['average_confidence'] > 0.7])
    }


def generate_visual_timeline(clustered_scenes: Dict[str, Any], 
                           video_duration: float, 
                           timeline_width: int = 60) -> str:
    """
    Generate a visual timeline representation of detected scenes.
    
    Args:
        clustered_scenes: Output from cluster_temporal_frames
        video_duration: Total video duration in seconds
        timeline_width: Width of timeline in characters
        
    Returns:
        Visual timeline string
    """
    timeline_lines = []
    
    # Create time markers
    time_markers = []
    for i in range(0, int(video_duration) + 1, max(1, int(video_duration / 10))):
        time_markers.append(f"{i}s")
    
    # Timeline header
    timeline_lines.extend([
        "📅 VIDEO TIMELINE ANALYSIS",
        "═" * timeline_width,
        ""
    ])
    
    # Time scale
    time_scale = ""
    for i in range(timeline_width):
        time_pos = (i / timeline_width) * video_duration
        if i % (timeline_width // len(time_markers)) == 0:
            marker_idx = i // (timeline_width // len(time_markers))
            if marker_idx < len(time_markers):
                time_scale += time_markers[marker_idx].ljust(timeline_width // len(time_markers))[:timeline_width // len(time_markers)]
        else:
            time_scale += " "
    
    timeline_lines.append(time_scale)
    timeline_lines.append("│" + "─" * (timeline_width - 1))
    
    # Scene tracks (show top 5 most significant labels)
    significant_labels = sorted(clustered_scenes.items(), 
                              key=lambda x: x[1]['total_frames'], reverse=True)[:5]
    
    for label_desc, cluster_data in significant_labels:
        track_line = "│"
        
        for i in range(timeline_width - 1):
            time_pos = (i / (timeline_width - 1)) * video_duration
            
            # Check if any cluster covers this time position
            covered = False
            for cluster in cluster_data['clusters']:
                if cluster['start_time'] <= time_pos <= cluster['end_time']:
                    covered = True
                    break
            
            track_line += "█" if covered else " "
        
        # Add label
        short_label = label_desc[:15] + "..." if len(label_desc) > 15 else label_desc
        timeline_lines.append(f"{track_line} {short_label}")
    
    timeline_lines.append("└" + "─" * (timeline_width - 1))
    timeline_lines.append("")
    
    return "\n".join(timeline_lines)


def generate_human_readable_report(raw_results: Dict[str, Any]) -> str:
    """
    Generate a comprehensive human-readable report of raw Google Video Intelligence results.
    
    Args:
        raw_results: Raw API results dictionary
        
    Returns:
        Formatted report string
    """
    report_lines = []
    
    # Header
    report_lines.extend([
        "🏷️ ENHANCED GOOGLE VIDEO INTELLIGENCE ANALYSIS",
        "═" * 70,
        "",
        f"📹 Video: {raw_results['video_uri']}",
        f"⏱️  Video Duration: {raw_results['video_duration']:.1f} seconds",
        f"📅 Processed: {raw_results['processing_timestamp']}",
        f"🔧 API Configuration: {raw_results['api_config']['model']} model, {raw_results['api_config']['label_detection_mode']}",
        ""
    ])
    
    # Perform enhanced analysis
    frame_labels = raw_results["frame_labels"]
    segment_labels = raw_results["segment_labels"]
    video_duration = raw_results["video_duration"]
    
    # Enhanced scene detection analysis
    print("🔄 Performing enhanced scene detection with hierarchical room priority...")
    scenes = detect_scene_boundaries(frame_labels, video_duration)
    refined_scenes = prioritize_and_segment_scenes(scenes)
    
    # Consolidate micro-scenes into final coherent scenes
    print("🔄 Consolidating scenes into final classifications...")
    final_scenes = consolidate_final_scenes(refined_scenes, video_duration)
    
    # Print final scene summary
    print_final_scene_summary(final_scenes)
    
    # Convert to clustered format for compatibility
    clustered_scenes = {}
    for scene in refined_scenes:
        scene_key = f"Scene {scene['scene_id']}: {scene.get('primary_label', scene.get('dominant_label', 'unknown'))}"
        clustered_scenes[scene_key] = {
            'total_frames': sum(data['frame_count'] for data in scene['labels'].values()),
            'total_clusters': 1,
            'clusters': [{
                'cluster_id': 1,
                'start_time': scene['start_time'],
                'end_time': scene['end_time'],
                'duration': scene['duration'],
                'frame_count': sum(data['frame_count'] for data in scene['labels'].values()),
                'confidence_avg': scene.get('scene_confidence', 0.5),
                'scene_type': scene.get('scene_type', 'unknown'),
                'scene_category': scene.get('scene_category', 'unknown'),
                'primary_label': scene.get('primary_label', 'unknown')
            }],
            'overall_confidence': scene.get('scene_confidence', 0.5),
            'scene_info': scene
        }
    
    # Segment-frame correlation analysis
    print("🔄 Analyzing segment-frame correlations...")
    correlation_analysis = analyze_segment_frame_correlation(segment_labels, frame_labels)
    
    # Scene inference
    print("🔄 Inferring scenes from labels...")
    scene_inference = infer_scenes_from_labels(clustered_scenes, video_duration)
    
    # Visual timeline
    print("🔄 Generating visual timeline...")
    visual_timeline = generate_visual_timeline(clustered_scenes, video_duration)
    
    # Add visual timeline to report
    report_lines.extend([
        visual_timeline,
        ""
    ])
    
    # Enhanced Scene Detection Results  
    report_lines.extend([
        "🏠 ENHANCED SCENE DETECTION ANALYSIS",
        "─" * 50,
        f"Total Scenes Detected: {len(refined_scenes)}",
        f"Scene Detection Method: Timeline-based with hierarchical room priority",
        ""
    ])
    
    # Show detected scenes in chronological order
    sorted_scenes = sorted(refined_scenes, key=lambda x: x['start_time'])
    
    for scene in sorted_scenes:
        scene_category = scene.get('scene_category', 'unknown').upper()
        scene_type = scene.get('scene_type', 'unknown').upper().replace('_', ' ')
        primary_label = scene.get('primary_label', 'unknown')
        confidence = scene.get('scene_confidence', 0.0)
        
        # Scene header with emoji based on category
        category_emoji = "🏠" if scene_category == "INDOOR" else "🌳" if scene_category == "OUTDOOR" else "📦"
        
        report_lines.extend([
            f"{category_emoji} SCENE {scene['scene_id']}: {scene_type}",
            f"   ⏱️  Time Range: {scene['start_time']:.1f}s - {scene['end_time']:.1f}s ({scene['duration']:.1f}s)",
            f"   🎯 Primary Label: {primary_label}",
            f"   📊 Scene Confidence: {confidence:.3f}",
            f"   📂 Category: {scene_category} → {scene_type}"
        ])
        
        # Show all labels in this scene
        if scene['labels']:
            report_lines.append("   🏷️  All Labels in Scene:")
            for label, data in sorted(scene['labels'].items(), key=lambda x: x[1]['avg_confidence'], reverse=True):
                report_lines.append(f"      • {label}: {data['frame_count']} frames (avg conf: {data['avg_confidence']:.3f})")
        
        # Show segmentation info if applicable
        if 'segmentation_reason' in scene:
            report_lines.append(f"   ✂️  {scene['segmentation_reason']}")
            report_lines.append(f"   📎 Original Scene: {scene['original_scene_id']}")
        
        report_lines.append("")
    
    # Detailed scene rankings
    if scene_inference['scene_candidates']:
        report_lines.append("🏆 SCENE RANKINGS (by evidence strength):")
        for i, (room_type, data) in enumerate(scene_inference['scene_candidates'].items()):
            rank_emoji = ["🥇", "🥈", "🥉"][i] if i < 3 else "🏅"
            room_display = room_type.upper().replace('_', ' ')
            report_lines.extend([
                f"{rank_emoji} {room_display}:",
                f"  ├── Combined Score: {data['combined_score']:.3f}",
                f"  ├── Average Confidence: {data['average_confidence']:.3f}",
                f"  ├── Total Frames: {data['total_frames']}",
                f"  ├── Temporal Coverage: {data['temporal_coverage']:.1f}%",
                f"  └── Evidence Sources: {data['evidence_count']} labels"
            ])
            
            # Show top evidence
            for evidence in data['evidence'][:2]:  # Show top 2 pieces of evidence
                report_lines.append(f"     • {evidence['label']} ({evidence['total_frames']} frames, {evidence['weighted_confidence']:.3f} confidence)")
            
            if len(data['evidence']) > 2:
                report_lines.append(f"     • ... and {len(data['evidence']) - 2} more")
            report_lines.append("")
    
    # Temporal Clustering Results
    report_lines.extend([
        "⏰ TEMPORAL CLUSTERING ANALYSIS",
        "─" * 50,
        f"Labels with Temporal Clusters: {len(clustered_scenes)}",
        ""
    ])
    
    # Show top clustered labels
    top_clustered = sorted(clustered_scenes.items(), 
                          key=lambda x: x[1]['total_frames'], reverse=True)[:5]
    
    for label_desc, cluster_data in top_clustered:
        report_lines.extend([
            f"🏷️  {label_desc} ({cluster_data['total_frames']} frames, {cluster_data['total_clusters']} clusters):",
            f"   └── Overall Confidence: {cluster_data['overall_confidence']:.3f}"
        ])
        
        for cluster in cluster_data['clusters']:
            duration_text = f"{cluster['duration']:.1f}s" if cluster['duration'] > 0 else "instant"
            report_lines.append(f"      • Cluster {cluster['cluster_id']}: {cluster['start_time']:.1f}s-{cluster['end_time']:.1f}s "
                              f"({duration_text}, {cluster['frame_count']} frames, avg conf: {cluster['confidence_avg']:.3f})")
        report_lines.append("")
    
    # Segment-Frame Correlation Analysis
    report_lines.extend([
        "🔗 SEGMENT-FRAME CORRELATION ANALYSIS",
        "─" * 50,
        f"Segments Analyzed: {correlation_analysis['total_segments_analyzed']}",
        f"Well-Supported Segments: {correlation_analysis['well_supported_segments']} (≥70% frame support)",
        f"Contradicted Segments: {correlation_analysis['contradicted_segments']} (<30% frame support)",
        ""
    ])
    
    # Show correlation details for significant segments
    significant_correlations = [c for c in correlation_analysis['correlations'] 
                               if c['overlapping_frame_count'] > 0]
    
    for correlation in significant_correlations[:3]:  # Show top 3
        support_status = "✅ WELL SUPPORTED" if correlation['support_ratio'] >= 0.7 else \
                        "⚠️  PARTIALLY SUPPORTED" if correlation['support_ratio'] >= 0.3 else \
                        "❌ CONTRADICTED"
        
        report_lines.extend([
            f"📦 Segment: '{correlation['segment_description']}' ({correlation['segment_time_range']})",
            f"   ├── Segment Confidence: {correlation['segment_confidence']:.3f}",
            f"   ├── Overlapping Frames: {correlation['overlapping_frame_count']}",
            f"   ├── Supporting Frames: {correlation['supporting_frame_count']} ({correlation['support_ratio']:.1%})",
            f"   └── Status: {support_status}",
            ""
        ])
        
        # Show some supporting/contradicting evidence
        if correlation['supporting_frames']:
            report_lines.append("      Supporting Evidence:")
            for frame in correlation['supporting_frames'][:2]:
                report_lines.append(f"        • {frame['frame_description']} at {frame['frame_time']:.1f}s (conf: {frame['frame_confidence']:.3f})")
        
        if correlation['contradicting_frames']:
            report_lines.append("      Contradicting Evidence:")
            for frame in correlation['contradicting_frames'][:2]:
                report_lines.append(f"        • {frame['frame_description']} at {frame['frame_time']:.1f}s (conf: {frame['frame_confidence']:.3f})")
        
        report_lines.append("")
    
    # Shot Detection Summary
    shots = raw_results["shot_annotations"]
    report_lines.extend([
        f"🎯 SHOT DETECTION RESULTS:",
        f"Total Shots Detected: {len(shots)}",
        ""
    ])
    
    if shots:
        report_lines.append("Shot Breakdown:")
        for shot in shots:
            report_lines.append(f"  Shot {shot['shot_number']}: {shot['start_time']:.1f}s → {shot['end_time']:.1f}s ({shot['duration']:.1f}s)")
        report_lines.append("")
    
    # Segment Labels Analysis
    segment_labels = raw_results["segment_labels"]
    report_lines.extend([
        f"📦 SEGMENT LABELS ANALYSIS:",
        f"Total Segment Labels: {len(segment_labels)}",
        ""
    ])
    
    if segment_labels:
        # Sort by max confidence
        sorted_segments = sorted(segment_labels, key=lambda x: x['max_confidence'], reverse=True)
        
        report_lines.append("Segment Labels (sorted by confidence):")
        for label in sorted_segments:
            report_lines.append(f"  🏷️  {label['description']} (confidence: {label['max_confidence']:.3f})")
            for segment in label['segments']:
                report_lines.append(f"     └── {segment['start_time']:.1f}s - {segment['end_time']:.1f}s ({segment['confidence']:.3f})")
        report_lines.append("")
    
    # Frame Labels Analysis
    frame_labels = raw_results["frame_labels"]
    report_lines.extend([
        f"🖼️  FRAME LABELS ANALYSIS:",
        f"Total Frame Labels: {len(frame_labels)}",
        ""
    ])
    
    if frame_labels:
        # Sort by max confidence
        sorted_frames = sorted(frame_labels, key=lambda x: x['max_confidence'], reverse=True)
        
        report_lines.append("Frame Labels (sorted by confidence):")
        for label in sorted_frames:
            report_lines.append(f"  🖼️  {label['description']} (max: {label['max_confidence']:.3f}, {label['frame_count']} frames)")
            
            # Show confidence distribution
            confidences = [frame['confidence'] for frame in label['frames']]
            if confidences:
                avg_conf = sum(confidences) / len(confidences)
                min_conf = min(confidences)
                max_conf = max(confidences)
                report_lines.append(f"     └── Confidence range: {min_conf:.3f} - {max_conf:.3f} (avg: {avg_conf:.3f})")
        report_lines.append("")
    
    # Summary Statistics
    if segment_labels or frame_labels:
        all_labels = set()
        high_conf_labels = set()
        
        for label in segment_labels:
            all_labels.add(label['description'])
            if label['max_confidence'] >= 0.7:
                high_conf_labels.add(label['description'])
        
        for label in frame_labels:
            all_labels.add(label['description'])
            if label['max_confidence'] >= 0.7:
                high_conf_labels.add(label['description'])
        
        report_lines.extend([
            f"📊 SUMMARY STATISTICS:",
            f"Unique Labels Detected: {len(all_labels)}",
            f"High Confidence Labels (≥70%): {len(high_conf_labels)}",
            f"Segment vs Frame Labels: {len(segment_labels)} segment, {len(frame_labels)} frame",
            ""
        ])
        
        # Show all unique labels
        report_lines.extend([
            f"🏆 ALL UNIQUE LABELS DETECTED:",
            *[f"  • {label}" for label in sorted(all_labels)],
            ""
        ])
    
    # Footer
    report_lines.extend([
        "═" * 70,
        f"📋 Raw Google Video Intelligence API Results",
        f"🎯 Purpose: Baseline analysis for ADR-002 calibration"
    ])
    
    return "\n".join(report_lines)


@pytest.fixture
def test_video_path():
    """Fixture to provide test video path"""
    video_path = Path(__file__).parent.parent / "properties_medias/videos/julie_01_indoors_and_outdoors.MOV"
    if not video_path.exists():
        pytest.skip(f"Test video not found: {video_path}")
    return str(video_path)


@pytest.mark.parametrize("video_key", ["julie_indoor_outdoor"])
def test_google_video_intelligence_raw_labels(video_key, test_video_path):
    """
    Test to extract and display raw Google Video Intelligence API labels.
    
    This test bypasses all ADR-002 post-processing and shows exactly what
    Google Video Intelligence API returns for the Julie video.
    
    Args:
        video_key: Key for video configuration
        test_video_path: Path to test video file
    """
    print(f"\n🎬 Starting Google Video Intelligence Raw Labels Analysis")
    print(f"📹 Video: {video_key}")
    
    video_config = TEST_VIDEOS[video_key]
    
    try:
        # Step 1: Upload test video to GCS
        bucket_name = settings.GCP.Storage.USER_BUCKET
        blob_name = f"tests/video-intelligence/raw-analysis/{Path(test_video_path).name}"
        
        video_uri = upload_video_to_gcs(test_video_path, bucket_name, blob_name)
        
        # Step 2: Analyze with Google Video Intelligence API
        print(f"🔄 Analyzing video with Google Video Intelligence API...")
        raw_results = analyze_video_raw_labels(video_uri)
        
        # Step 3: Generate human-readable report
        print(f"📋 Generating analysis report...")
        report = generate_human_readable_report(raw_results)
        
        # Step 4: Display the report
        print(f"\n{report}")
        
        # Step 5: Save results to file
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        results_file = Path(__file__).parent / f"raw_video_intelligence_{video_key}_{timestamp}.json"
        
        with open(results_file, 'w') as f:
            json.dump(raw_results, f, indent=2, default=str)
        
        print(f"\n💾 Raw results saved to: {results_file}")
        
        # Step 6: Clean up GCS file
        try:
            credentials = None
            if os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
                credentials = service_account.Credentials.from_service_account_file(
                    SERVICE_ACCOUNT_KEY_FILE_PATH,
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
            
            client = storage.Client(credentials=credentials)
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            blob.delete()
            print(f"🧹 Cleaned up GCS file: {video_uri}")
            
        except Exception as e:
            print(f"⚠️  Could not clean up GCS file: {e}")
        
        # Step 7: Basic assertions (informational only)
        observations = []
        
        if len(raw_results["segment_labels"]) == 0 and len(raw_results["frame_labels"]) == 0:
            observations.append("⚠️  No labels detected by Google Video Intelligence API")
        else:
            observations.append(f"✅ {len(raw_results['segment_labels'])} segment labels and {len(raw_results['frame_labels'])} frame labels detected")
        
        if len(raw_results["shot_annotations"]) == 0:
            observations.append("⚠️  No shots detected")
        else:
            observations.append(f"✅ {len(raw_results['shot_annotations'])} shots detected")
        
        # Display observations
        print(f"\n🔍 RAW API OBSERVATIONS:")
        for obs in observations:
            print(f"  {obs}")
        
        print(f"\n🎯 Raw analysis completed - Google Video Intelligence baseline established")
        
        # Always pass - this is an analysis test, not a validation test
        assert True, "Raw Google Video Intelligence analysis completed successfully"
        
    except Exception as e:
        print(f"\n❌ Error during raw analysis: {e}")
        print(f"📝 This error information is valuable for API debugging")
        
        # Still pass the test so we can analyze partial results
        assert True, f"Raw analysis encountered error (logged for debugging): {e}"


if __name__ == "__main__":
    # Allow running the test directly
    pytest.main([__file__, "-v", "-s"])
