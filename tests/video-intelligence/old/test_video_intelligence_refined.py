#!/usr/bin/env python3
"""
Refined Video Intelligence API test with enhanced scene detection
This script implements the optimized approach for real estate video room/scene detection
"""

import os
import sys
from pathlib import Path
import json
from typing import List, Dict, Any, Tuple
from collections import defaultdict
import statistics

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from google.cloud import videointelligence_v1 as videointelligence
from google.cloud import storage
from google.oauth2 import service_account
from config.config import settings

# Service account paths (same as used in other modules)
SERVICE_ACCOUNT_KEY_FILE_PATH = 'secrets/editora-prod-f0da3484f1a0.json'


def upload_video_to_gcs(local_video_path: str, bucket_name: str, blob_name: str) -> str:
    """Upload video to Google Cloud Storage and return the GCS URI."""
    print(f"📤 Uploading {local_video_path} to gs://{bucket_name}/{blob_name}")
    
    # Set up credentials (same pattern as other modules)
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


def filter_scene_labels_advanced(labels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Advanced filtering to focus on scene/room labels while excluding furniture/details.
    """
    # Scene/room related keywords (positive filter)
    scene_keywords = {
        'room', 'bedroom', 'bathroom', 'kitchen', 'living', 'dining', 'office', 
        'hallway', 'corridor', 'lobby', 'entrance', 'foyer', 'balcony', 'patio',
        'garden', 'yard', 'interior', 'exterior', 'indoor', 'outdoor', 'space', 
        'area', 'zone', 'chamber', 'suite', 'studio', 'loft', 'basement', 'attic',
        'garage', 'closet', 'pantry', 'den', 'study', 'library', 'conservatory'
    }
    
    # Non-scene keywords to exclude (negative filter)
    exclude_keywords = {
        'flooring', 'tile', 'floor', 'ceiling', 'wall', 'furniture', 'table', 
        'chair', 'sofa', 'bed', 'cabinet', 'countertop', 'appliance', 'lamp',
        'curtain', 'window', 'door', 'handle', 'knob', 'fixture', 'faucet',
        'sink', 'toilet', 'shower', 'bathtub', 'mirror', 'painting', 'artwork',
        'plant', 'vase', 'book', 'pillow', 'blanket', 'rug', 'carpet'
    }
    
    filtered_labels = []
    
    for label in labels:
        description_lower = label['description'].lower()
        
        # Check if it's scene-related and not excluded
        is_scene_related = any(keyword in description_lower for keyword in scene_keywords)
        is_excluded = any(keyword in description_lower for keyword in exclude_keywords)
        
        # Include if scene-related and not explicitly excluded
        if is_scene_related and not is_excluded:
            label['filtered_reason'] = 'scene_related'
            filtered_labels.append(label)
        elif not is_excluded and label.get('max_confidence', 0) >= 0.8:
            # Include high-confidence labels that aren't explicitly excluded
            label['filtered_reason'] = 'high_confidence'
            filtered_labels.append(label)
    
    return filtered_labels


def aggregate_scenes_from_frames(frame_labels: List[Dict[str, Any]], 
                                shot_annotations: List[Dict[str, Any]],
                                video_duration: float) -> List[Dict[str, Any]]:
    """
    Aggregate high-confidence frame labels into scene segments using temporal clustering.
    """
    if not frame_labels:
        return []
    
    # Group frame labels by description and time proximity
    scene_groups = defaultdict(list)
    
    for label in frame_labels:
        description = label['description']
        for frame in label.get('frames', []):
            scene_groups[description].append({
                'time': frame['time_offset'],
                'confidence': frame['confidence'],
                'description': description
            })
    
    # Create scene segments
    scenes = []
    
    for description, frames in scene_groups.items():
        if len(frames) < 2:  # Skip if not enough temporal evidence
            continue
            
        # Sort frames by time
        frames.sort(key=lambda x: x['time'])
        
        # Calculate scene boundaries using temporal clustering
        scene_start = frames[0]['time']
        scene_end = frames[-1]['time']
        
        # Use shot boundaries if available to refine scene boundaries
        if shot_annotations:
            for shot in shot_annotations:
                if shot['start_time'] <= scene_start <= shot['end_time']:
                    scene_start = max(scene_start, shot['start_time'])
                if shot['start_time'] <= scene_end <= shot['end_time']:
                    scene_end = min(scene_end, shot['end_time'])
        
        # Calculate average confidence
        avg_confidence = statistics.mean([f['confidence'] for f in frames])
        
        # Calculate keyframe timestamp (midpoint)
        keyframe_timestamp = (scene_start + scene_end) / 2
        
        scenes.append({
            'scene_type': description,
            'start_time': scene_start,
            'end_time': scene_end,
            'duration': scene_end - scene_start,
            'confidence': avg_confidence,
            'keyframe_timestamp': keyframe_timestamp,
            'frame_count': len(frames),
            'supporting_frames': frames
        })
    
    # Sort scenes by start time and merge overlapping ones
    scenes.sort(key=lambda x: x['start_time'])
    merged_scenes = []
    
    for scene in scenes:
        if not merged_scenes:
            merged_scenes.append(scene)
        else:
            last_scene = merged_scenes[-1]
            # Merge if scenes overlap significantly or are very close
            if (scene['start_time'] <= last_scene['end_time'] + 2.0 and 
                scene['scene_type'] == last_scene['scene_type']):
                # Merge scenes
                last_scene['end_time'] = max(last_scene['end_time'], scene['end_time'])
                last_scene['duration'] = last_scene['end_time'] - last_scene['start_time']
                last_scene['keyframe_timestamp'] = (last_scene['start_time'] + last_scene['end_time']) / 2
                last_scene['confidence'] = max(last_scene['confidence'], scene['confidence'])
                last_scene['frame_count'] += scene['frame_count']
                last_scene['supporting_frames'].extend(scene['supporting_frames'])
            else:
                merged_scenes.append(scene)
    
    return merged_scenes


def analyze_video_refined_approach(video_uri: str, config_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze video with refined configuration optimized for scene/room detection.
    """
    print(f"\n🎬 REFINED ANALYSIS: {config_name}")
    print(f"📹 Video: {video_uri}")
    print(f"⚙️  Config: {json.dumps(config, indent=2)}")
    print("=" * 80)
    
    # Set up credentials
    credentials = None
    if os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_KEY_FILE_PATH,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
    
    client = videointelligence.VideoIntelligenceServiceClient(credentials=credentials)

    # Configure features
    features = []
    video_context = {}
    
    # Label detection configuration
    if config.get("use_label_detection", True):
        features.append(videointelligence.Feature.LABEL_DETECTION)
        
        label_config = {
            "label_detection_mode": getattr(
                videointelligence.LabelDetectionMode, 
                config.get("label_detection_mode", "SHOT_AND_FRAME_MODE")
            ),
            "model": config.get("model", "builtin/stable")
        }
        
        # Add confidence thresholds
        if "frame_confidence_threshold" in config:
            label_config["frame_confidence_threshold"] = config["frame_confidence_threshold"]
        if "video_confidence_threshold" in config:
            label_config["video_confidence_threshold"] = config["video_confidence_threshold"]
            
        video_context["label_detection_config"] = label_config
    
    # Enhanced shot detection configuration
    if config.get("use_shot_detection", True):
        features.append(videointelligence.Feature.SHOT_CHANGE_DETECTION)
        
        # Add shot detection configuration for better sensitivity
        shot_config = {
            "model": config.get("shot_detection_model", "builtin/stable")
        }
        video_context["shot_change_detection_config"] = shot_config

    # Make the API request
    operation = client.annotate_video(
        request={
            "input_uri": video_uri,
            "features": features,
            "video_context": video_context
        }
    )

    print("🔄 Processing video with refined configuration...")
    result = operation.result(timeout=600)  # 10 minute timeout

    # Process results
    print(f"\n📊 RAW RESULTS FOR: {config_name}")
    print("-" * 60)
    
    raw_segment_labels = []
    raw_frame_labels = []
    shot_annotations = []
    video_duration = 0
    
    for annotation_result in result.annotation_results:
        # Get video duration
        if hasattr(annotation_result, 'input_uri'):
            # Try to get duration from shot annotations
            if annotation_result.shot_annotations:
                last_shot = annotation_result.shot_annotations[-1]
                video_duration = (last_shot.end_time_offset.seconds + 
                                last_shot.end_time_offset.microseconds / 1e6)
        
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
                
                shot_annotations.append({
                    "shot_number": i+1,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration
                })
        
        # Process segment labels (shot-level)
        if annotation_result.segment_label_annotations:
            print(f"\n🏠 RAW SEGMENT LABELS: {len(annotation_result.segment_label_annotations)} labels")
            
            for label_annotation in annotation_result.segment_label_annotations:
                max_confidence = max(segment.confidence for segment in label_annotation.segments)
                
                print(f"   📦 '{label_annotation.entity.description}' (Max confidence: {max_confidence:.3f})")
                
                # Store raw label data
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
            print(f"\n🖼️  RAW FRAME LABELS: {len(annotation_result.frame_label_annotations)} labels")
            
            for label_annotation in annotation_result.frame_label_annotations:
                max_confidence = max(frame.confidence for frame in label_annotation.frames)
                
                print(f"   🖼️  '{label_annotation.entity.description}' (Max confidence: {max_confidence:.3f})")
                
                # Store raw frame label data
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

    # Apply advanced filtering
    print(f"\n🔍 APPLYING ADVANCED FILTERING")
    print("-" * 40)
    
    filtered_segment_labels = filter_scene_labels_advanced(raw_segment_labels)
    filtered_frame_labels = filter_scene_labels_advanced(raw_frame_labels)
    
    print(f"Segment labels: {len(raw_segment_labels)} → {len(filtered_segment_labels)} (filtered)")
    print(f"Frame labels: {len(raw_frame_labels)} → {len(filtered_frame_labels)} (filtered)")
    
    # Display filtered results
    if filtered_segment_labels:
        print(f"\n✨ FILTERED SEGMENT LABELS:")
        for label in filtered_segment_labels:
            reason = label.get('filtered_reason', 'unknown')
            print(f"   🏠 '{label['description']}' (confidence: {label['max_confidence']:.3f}, reason: {reason})")
    
    if filtered_frame_labels:
        print(f"\n✨ FILTERED FRAME LABELS:")
        for label in filtered_frame_labels:
            reason = label.get('filtered_reason', 'unknown')
            print(f"   🏠🖼️  '{label['description']}' (confidence: {label['max_confidence']:.3f}, reason: {reason})")

    # Aggregate scenes from frame data
    print(f"\n🎭 SCENE AGGREGATION")
    print("-" * 40)
    
    aggregated_scenes = aggregate_scenes_from_frames(filtered_frame_labels, shot_annotations, video_duration)
    
    if aggregated_scenes:
        print(f"📍 DETECTED SCENES: {len(aggregated_scenes)} scenes")
        for i, scene in enumerate(aggregated_scenes):
            print(f"   Scene {i+1}: '{scene['scene_type']}'")
            print(f"     ⏱️  Time: {scene['start_time']:.1f}s → {scene['end_time']:.1f}s (Duration: {scene['duration']:.1f}s)")
            print(f"     🎯 Keyframe: {scene['keyframe_timestamp']:.1f}s")
            print(f"     ✨ Confidence: {scene['confidence']:.3f}")
            print(f"     📊 Frame evidence: {scene['frame_count']} frames")
    else:
        print("❌ No scenes detected after aggregation")

    # Calculate metrics
    total_raw_labels = len(raw_segment_labels) + len(raw_frame_labels)
    total_filtered_labels = len(filtered_segment_labels) + len(filtered_frame_labels)
    high_confidence_labels = sum(1 for label in filtered_segment_labels + filtered_frame_labels 
                                if label.get('max_confidence', 0) >= 0.7)
    
    filtering_efficiency = ((total_raw_labels - total_filtered_labels) / total_raw_labels * 100 
                          if total_raw_labels > 0 else 0)
    quality_score = (high_confidence_labels / total_filtered_labels * 100 
                    if total_filtered_labels > 0 else 0)
    
    print(f"\n📈 REFINED ANALYSIS METRICS")
    print("-" * 40)
    print(f"Raw labels: {total_raw_labels}")
    print(f"Filtered labels: {total_filtered_labels}")
    print(f"Filtering efficiency: {filtering_efficiency:.1f}%")
    print(f"High confidence labels: {high_confidence_labels} ({quality_score:.1f}%)")
    print(f"Detected scenes: {len(aggregated_scenes)}")
    print(f"Shot boundaries: {len(shot_annotations)}")
    
    # Return comprehensive results
    return {
        "config_name": config_name,
        "config": config,
        "video_uri": video_uri,
        "video_duration": video_duration,
        "raw_results": {
            "segment_labels": raw_segment_labels,
            "frame_labels": raw_frame_labels,
            "shot_annotations": shot_annotations
        },
        "filtered_results": {
            "segment_labels": filtered_segment_labels,
            "frame_labels": filtered_frame_labels
        },
        "aggregated_scenes": aggregated_scenes,
        "metrics": {
            "total_raw_labels": total_raw_labels,
            "total_filtered_labels": total_filtered_labels,
            "filtering_efficiency": filtering_efficiency,
            "quality_score": quality_score,
            "scene_count": len(aggregated_scenes),
            "shot_count": len(shot_annotations)
        }
    }


def test_refined_configurations():
    """
    Test refined Video Intelligence configurations with enhanced post-processing.
    """
    # Path to the test video
    video_path = Path(__file__).parent.parent / "properties_medias" / "videos" / "two_rooms.mp4"
    
    assert video_path.exists(), f"Video file not found: {video_path}"
    
    # Upload video to GCS
    bucket_name = settings.GCP.Storage.USER_BUCKET
    blob_name = "tests/video-intelligence/two_rooms_refined.mp4"
    
    video_uri = upload_video_to_gcs(
        local_video_path=str(video_path),
        bucket_name=bucket_name,
        blob_name=blob_name
    )
    
    # Define refined configurations to test
    refined_configurations = {
        "high_confidence_refined": {
            "use_label_detection": True,
            "label_detection_mode": "SHOT_AND_FRAME_MODE",
            "model": "builtin/stable",
            "video_confidence_threshold": 0.8,
            "frame_confidence_threshold": 0.8,
            "use_shot_detection": True,
            "shot_detection_model": "builtin/stable"
        },
        "balanced_refined": {
            "use_label_detection": True,
            "label_detection_mode": "SHOT_AND_FRAME_MODE",
            "model": "builtin/stable",
            "video_confidence_threshold": 0.7,
            "frame_confidence_threshold": 0.8,
            "use_shot_detection": True,
            "shot_detection_model": "builtin/stable"
        },
        "temporal_focused": {
            "use_label_detection": True,
            "label_detection_mode": "SHOT_AND_FRAME_MODE",
            "model": "builtin/latest",
            "video_confidence_threshold": 0.7,
            "frame_confidence_threshold": 0.75,
            "use_shot_detection": True,
            "shot_detection_model": "builtin/stable"
        }
    }
    
    all_results = {}
    
    print(f"🎥 TESTING REFINED CONFIGURATIONS FOR SCENE DETECTION")
    print(f"📁 Video: {video_path}")
    print(f"🔬 Configurations: {len(refined_configurations)}")
    
    for config_name, config in refined_configurations.items():
        try:
            print(f"\n" + "="*100)
            results = analyze_video_refined_approach(video_uri, config_name, config)
            all_results[config_name] = results
            
        except Exception as e:
            print(f"❌ Error testing {config_name}: {str(e)}")
            import traceback
            traceback.print_exc()
            continue
    
    # Save all results
    output_file = Path(__file__).parent / "refined_configurations_results.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\n📄 All results saved to: {output_file}")
    
    # Compare configurations
    print(f"\n🏆 REFINED CONFIGURATION COMPARISON")
    print("=" * 100)
    
    best_config = None
    best_score = 0
    
    for config_name, results in all_results.items():
        metrics = results.get("metrics", {})
        scene_count = metrics.get("scene_count", 0)
        quality_score = metrics.get("quality_score", 0)
        filtering_efficiency = metrics.get("filtering_efficiency", 0)
        
        # Combined score: 40% scene detection + 40% quality + 20% filtering efficiency
        combined_score = (scene_count * 20) + (quality_score * 0.4) + (filtering_efficiency * 0.2)
        
        print(f"\n{config_name.upper()}:")
        print(f"  🎭 Detected scenes: {scene_count}")
        print(f"  ✨ Quality score: {quality_score:.1f}%")
        print(f"  🔍 Filtering efficiency: {filtering_efficiency:.1f}%")
        print(f"  🎯 Combined score: {combined_score:.1f}")
        
        # Show detected scenes
        scenes = results.get("aggregated_scenes", [])
        if scenes:
            print(f"  📍 Scene details:")
            for i, scene in enumerate(scenes):
                print(f"     {i+1}. '{scene['scene_type']}' ({scene['start_time']:.1f}s-{scene['end_time']:.1f}s, "
                      f"confidence: {scene['confidence']:.3f})")
        
        if combined_score > best_score:
            best_score = combined_score
            best_config = config_name
    
    if best_config:
        print(f"\n🥇 BEST REFINED CONFIGURATION: {best_config.upper()}")
        print(f"   🎯 Score: {best_score:.1f}")
        print(f"   ✅ Recommended for production use in real estate video scene detection")
        
        # Show production-ready configuration
        best_results = all_results[best_config]
        best_config_details = best_results['config']
        
        print(f"\n🔧 PRODUCTION-READY CONFIG:")
        print(json.dumps(best_config_details, indent=2))
    
    return all_results


def test_video_intelligence_refined_configurations():
    """Pytest-compatible test function."""
    results = test_refined_configurations()
    
    # Assert that we got results for at least one configuration
    assert len(results) > 0, "No configurations produced results"
    
    # Assert that at least one configuration detected scenes
    scenes_detected = False
    for config_results in results.values():
        if len(config_results.get("aggregated_scenes", [])) > 0:
            scenes_detected = True
            break
    
    assert scenes_detected, "No scenes detected in any configuration"
    
    # Assert quality metrics are reasonable
    for config_name, config_results in results.items():
        metrics = config_results.get("metrics", {})
        quality_score = metrics.get("quality_score", 0)
        filtering_efficiency = metrics.get("filtering_efficiency", 0)
        
        # Quality should be at least 50% and filtering should remove some noise
        assert quality_score >= 50, f"Quality score too low for {config_name}: {quality_score}%"
        assert filtering_efficiency >= 10, f"Filtering not effective for {config_name}: {filtering_efficiency}%"
    
    return results


def main():
    """Main function for standalone execution."""
    test_refined_configurations()


if __name__ == "__main__":
    main()
