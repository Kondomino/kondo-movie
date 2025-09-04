#!/usr/bin/env python3
"""
Optimized test script for Google Video Intelligence API focusing on room/scene detection
This script tests different configurations to get better results for real estate videos
"""

import os
import sys
from pathlib import Path
import json

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
    print(f"Uploading {local_video_path} to gs://{bucket_name}/{blob_name}")
    
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


def analyze_video_optimized_for_scenes(video_uri: str, config_name: str, config: dict):
    """Analyze video with optimized configuration for scene/room detection."""
    print(f"\n🎬 Testing Configuration: {config_name}")
    print(f"📹 Video: {video_uri}")
    print(f"⚙️  Config: {config}")
    print("=" * 80)
    
    # Set up credentials
    credentials = None
    if os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_KEY_FILE_PATH,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
    
    client = videointelligence.VideoIntelligenceServiceClient(credentials=credentials)

    # Configure features based on the test configuration
    features = []
    video_context = {}
    
    if config.get("use_label_detection", True):
        features.append(videointelligence.Feature.LABEL_DETECTION)
        
        # Configure label detection
        label_config = {
            "label_detection_mode": getattr(
                videointelligence.LabelDetectionMode, 
                config.get("label_detection_mode", "SHOT_AND_FRAME_MODE")
            ),
            "model": config.get("model", "builtin/stable")
        }
        
        # Add confidence thresholds if specified
        if "frame_confidence_threshold" in config:
            label_config["frame_confidence_threshold"] = config["frame_confidence_threshold"]
        if "video_confidence_threshold" in config:
            label_config["video_confidence_threshold"] = config["video_confidence_threshold"]
            
        video_context["label_detection_config"] = label_config
    
    if config.get("use_shot_detection", False):
        features.append(videointelligence.Feature.SHOT_CHANGE_DETECTION)
    
    # Make the API request
    operation = client.annotate_video(
        request={
            "input_uri": video_uri,
            "features": features,
            "video_context": video_context
        }
    )

    print("🔄 Processing video with optimized configuration...")
    result = operation.result(timeout=600)  # 10 minute timeout

    # Analyze and display results
    print(f"\n📊 RESULTS FOR: {config_name}")
    print("-" * 60)
    
    total_labels = 0
    high_confidence_labels = 0
    scene_related_labels = 0
    
    # Define scene/room related keywords to focus on
    scene_keywords = {
        'room', 'bedroom', 'bathroom', 'kitchen', 'living', 'dining', 'office', 'hallway', 
        'corridor', 'lobby', 'entrance', 'foyer', 'balcony', 'patio', 'garden', 'yard',
        'interior', 'exterior', 'indoor', 'outdoor', 'space', 'area', 'zone', 'chamber',
        'suite', 'studio', 'loft', 'basement', 'attic', 'garage', 'closet', 'pantry'
    }
    
    results_data = {
        "config_name": config_name,
        "config": config,
        "video_uri": video_uri,
        "segment_labels": [],
        "frame_labels": [],
        "shot_annotations": []
    }
    
    for annotation_result in result.annotation_results:
        # Process shot change detection if enabled
        if config.get("use_shot_detection", False) and annotation_result.shot_annotations:
            print(f"\n🎯 SHOT DETECTION: {len(annotation_result.shot_annotations)} shots detected")
            for i, shot in enumerate(annotation_result.shot_annotations):
                start_time = (shot.start_time_offset.seconds + 
                            shot.start_time_offset.microseconds / 1e6)
                end_time = (shot.end_time_offset.seconds + 
                          shot.end_time_offset.microseconds / 1e6)
                print(f"   Shot {i+1}: {start_time:.1f}s → {end_time:.1f}s "
                      f"(Duration: {end_time-start_time:.1f}s)")
                
                results_data["shot_annotations"].append({
                    "shot_number": i+1,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": end_time - start_time
                })
        
        # Process segment labels (shot-level)
        if annotation_result.segment_label_annotations:
            print(f"\n🏠 SEGMENT LABELS: {len(annotation_result.segment_label_annotations)} labels")
            
            for label_annotation in annotation_result.segment_label_annotations:
                total_labels += 1
                label_desc = label_annotation.entity.description.lower()
                
                # Check if this is a scene-related label
                is_scene_related = any(keyword in label_desc for keyword in scene_keywords)
                if is_scene_related:
                    scene_related_labels += 1
                
                # Get highest confidence segment
                max_confidence = max(segment.confidence for segment in label_annotation.segments)
                if max_confidence >= 0.7:
                    high_confidence_labels += 1
                    confidence_indicator = "🟢"
                elif max_confidence >= 0.5:
                    confidence_indicator = "🟡"
                else:
                    confidence_indicator = "🔴"
                
                scene_indicator = "🏠" if is_scene_related else "📦"
                
                print(f"   {confidence_indicator}{scene_indicator} '{label_annotation.entity.description}' "
                      f"(Max confidence: {max_confidence:.3f})")
                
                # Store label data
                label_data = {
                    "description": label_annotation.entity.description,
                    "entity_id": label_annotation.entity.entity_id,
                    "is_scene_related": is_scene_related,
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
                
                results_data["segment_labels"].append(label_data)

        # Process frame labels if available
        if annotation_result.frame_label_annotations:
            print(f"\n🖼️  FRAME LABELS: {len(annotation_result.frame_label_annotations)} labels")
            
            for label_annotation in annotation_result.frame_label_annotations:
                total_labels += 1
                label_desc = label_annotation.entity.description.lower()
                
                # Check if this is a scene-related label
                is_scene_related = any(keyword in label_desc for keyword in scene_keywords)
                if is_scene_related:
                    scene_related_labels += 1
                
                # Get highest confidence frame
                max_confidence = max(frame.confidence for frame in label_annotation.frames)
                if max_confidence >= 0.7:
                    high_confidence_labels += 1
                
                # Only show scene-related frame labels to reduce noise
                if is_scene_related:
                    print(f"   🏠🖼️  '{label_annotation.entity.description}' "
                          f"(Max confidence: {max_confidence:.3f})")
                
                # Store frame label data (but only scene-related ones)
                if is_scene_related:
                    label_data = {
                        "description": label_annotation.entity.description,
                        "entity_id": label_annotation.entity.entity_id,
                        "is_scene_related": True,
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
                    
                    results_data["frame_labels"].append(label_data)

    # Summary
    print(f"\n📈 SUMMARY FOR {config_name}")
    print("-" * 40)
    print(f"Total labels: {total_labels}")
    print(f"High confidence (≥0.7): {high_confidence_labels}")
    print(f"Scene-related labels: {scene_related_labels}")
    print(f"Scene relevance: {scene_related_labels/total_labels*100:.1f}%" if total_labels > 0 else "No labels")
    print(f"Quality score: {high_confidence_labels/total_labels*100:.1f}%" if total_labels > 0 else "No labels")
    
    return results_data


def test_multiple_configurations():
    """Test multiple Video Intelligence configurations to find the best for room/scene detection."""
    
    # Path to the test video
    video_path = Path(__file__).parent / "videos" / "two_rooms.mp4"
    
    assert video_path.exists(), f"Video file not found: {video_path}"
    
    # Upload video to GCS
    bucket_name = settings.GCP.Storage.USER_BUCKET
    blob_name = "tests/video-intelligence/two_rooms_optimized.mp4"
    
    video_uri = upload_video_to_gcs(
        local_video_path=str(video_path),
        bucket_name=bucket_name,
        blob_name=blob_name
    )
    
    # Define different configurations to test
    test_configurations = {
        "shot_mode_only": {
            "use_label_detection": True,
            "label_detection_mode": "SHOT_MODE",
            "model": "builtin/stable",
            "video_confidence_threshold": 0.5,
            "use_shot_detection": True
        },
        "shot_mode_high_confidence": {
            "use_label_detection": True,
            "label_detection_mode": "SHOT_MODE",
            "model": "builtin/stable",
            "video_confidence_threshold": 0.7,
            "use_shot_detection": True
        },
        "shot_mode_latest_model": {
            "use_label_detection": True,
            "label_detection_mode": "SHOT_MODE",
            "model": "builtin/latest",
            "video_confidence_threshold": 0.6,
            "use_shot_detection": True
        },
        "frame_mode_filtered": {
            "use_label_detection": True,
            "label_detection_mode": "FRAME_MODE",
            "model": "builtin/stable",
            "frame_confidence_threshold": 0.8,
            "use_shot_detection": True
        },
        "combined_optimized": {
            "use_label_detection": True,
            "label_detection_mode": "SHOT_AND_FRAME_MODE",
            "model": "builtin/stable",
            "video_confidence_threshold": 0.6,
            "frame_confidence_threshold": 0.8,
            "use_shot_detection": True
        }
    }
    
    all_results = {}
    
    print(f"🎥 Testing {len(test_configurations)} optimized configurations for room/scene detection")
    print(f"📁 Video: {video_path}")
    
    for config_name, config in test_configurations.items():
        try:
            results = analyze_video_optimized_for_scenes(video_uri, config_name, config)
            all_results[config_name] = results
            
        except Exception as e:
            print(f"❌ Error testing {config_name}: {str(e)}")
            continue
    
    # Save all results
    output_file = Path(__file__).parent / "optimized_configurations_results.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    
    print(f"\n📄 All results saved to: {output_file}")
    
    # Find best configuration based on scene relevance and quality
    best_config = None
    best_score = 0
    
    print(f"\n🏆 CONFIGURATION COMPARISON")
    print("=" * 80)
    
    for config_name, results in all_results.items():
        segment_labels = results.get("segment_labels", [])
        total_labels = len(segment_labels)
        scene_related = sum(1 for label in segment_labels if label.get("is_scene_related", False))
        high_confidence = sum(1 for label in segment_labels if label.get("max_confidence", 0) >= 0.7)
        
        scene_relevance = scene_related / total_labels * 100 if total_labels > 0 else 0
        quality_score = high_confidence / total_labels * 100 if total_labels > 0 else 0
        
        # Combined score: 70% scene relevance + 30% quality
        combined_score = (scene_relevance * 0.7) + (quality_score * 0.3)
        
        print(f"{config_name}:")
        print(f"  📊 Total labels: {total_labels}")
        print(f"  🏠 Scene-related: {scene_related} ({scene_relevance:.1f}%)")
        print(f"  ✨ High confidence: {high_confidence} ({quality_score:.1f}%)")
        print(f"  🎯 Combined score: {combined_score:.1f}")
        print()
        
        if combined_score > best_score:
            best_score = combined_score
            best_config = config_name
    
    if best_config:
        print(f"🥇 BEST CONFIGURATION: {best_config} (Score: {best_score:.1f})")
        print(f"   Recommended for room/scene detection in real estate videos")
    
    return all_results


def test_video_intelligence_optimized_configurations():
    """Pytest-compatible test function."""
    results = test_multiple_configurations()
    
    # Assert that we got results for at least one configuration
    assert len(results) > 0, "No configurations produced results"
    
    # Assert that at least one configuration found scene-related labels
    scene_labels_found = False
    for config_results in results.values():
        segment_labels = config_results.get("segment_labels", [])
        if any(label.get("is_scene_related", False) for label in segment_labels):
            scene_labels_found = True
            break
    
    assert scene_labels_found, "No scene-related labels found in any configuration"
    
    return results


def main():
    """Main function for standalone execution."""
    test_multiple_configurations()


if __name__ == "__main__":
    main()
