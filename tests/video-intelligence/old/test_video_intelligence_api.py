#!/usr/bin/env python3
"""
Test script for Google Video Intelligence API using two_rooms.mp4
This script uploads the video to GCS and analyzes it with LABEL_DETECTION
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


def analyze_video_with_intelligence(video_uri: str):
    """Analyze a video for scene labels using Google Video Intelligence API."""
    print(f"🎬 Analyzing video: {video_uri}")
    print("=" * 80)
    
    # Set up credentials (same pattern as other modules)
    credentials = None
    if os.path.exists(SERVICE_ACCOUNT_KEY_FILE_PATH):
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_KEY_FILE_PATH,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
    
    client = videointelligence.VideoIntelligenceServiceClient(credentials=credentials)

    # Configure the request for label detection with SHOT_AND_FRAME_MODE
    features = [videointelligence.Feature.LABEL_DETECTION]
    operation = client.annotate_video(
        request={
            "input_uri": video_uri,
            "features": features,
            "video_context": {
                "label_detection_config": {
                    "label_detection_mode": videointelligence.LabelDetectionMode.SHOT_AND_FRAME_MODE,
                    "model": "builtin/stable"  # Stable model for consistent results
                }
            }
        }
    )

    # Wait for the operation to complete
    print("🔄 Processing video with Google Video Intelligence API...")
    print("This may take a few minutes depending on video length...")
    result = operation.result(timeout=600)  # 10 minute timeout

    # Process and display results
    print("\n📊 ANALYSIS RESULTS")
    print("=" * 80)
    
    total_labels = 0
    high_confidence_labels = 0
    
    for annotation_result in result.annotation_results:
        # Process segment-level labels (scenes/shots)
        if annotation_result.segment_label_annotations:
            print(f"\n🎯 SEGMENT LABELS (Scenes/Shots): {len(annotation_result.segment_label_annotations)} labels found")
            print("-" * 60)
            
            for label_annotation in annotation_result.segment_label_annotations:
                total_labels += 1
                label_desc = label_annotation.entity.description
                
                print(f"\n📌 Label: '{label_desc}'")
                print(f"   Entity ID: {label_annotation.entity.entity_id}")
                
                # Show segments where this label appears
                for i, segment in enumerate(label_annotation.segments):
                    start_time = (segment.segment.start_time_offset.seconds + 
                                segment.segment.start_time_offset.microseconds / 1e6)
                    end_time = (segment.segment.end_time_offset.seconds + 
                              segment.segment.end_time_offset.microseconds / 1e6)
                    confidence = segment.confidence
                    
                    if confidence >= 0.7:
                        high_confidence_labels += 1
                        confidence_indicator = "🟢"
                    elif confidence >= 0.5:
                        confidence_indicator = "🟡"
                    else:
                        confidence_indicator = "🔴"
                    
                    print(f"   {confidence_indicator} Segment {i+1}: {start_time:.1f}s → {end_time:.1f}s "
                          f"(Duration: {end_time-start_time:.1f}s, Confidence: {confidence:.3f})")

        # Process frame-level labels if available
        if annotation_result.frame_label_annotations:
            print(f"\n🖼️  FRAME LABELS: {len(annotation_result.frame_label_annotations)} labels found")
            print("-" * 60)
            
            for label_annotation in annotation_result.frame_label_annotations:
                total_labels += 1
                label_desc = label_annotation.entity.description
                
                print(f"\n📌 Frame Label: '{label_desc}'")
                
                # Show frames where this label appears (limit to first 5 for readability)
                for i, frame in enumerate(label_annotation.frames[:5]):
                    time_offset = (frame.time_offset.seconds + 
                                 frame.time_offset.microseconds / 1e6)
                    confidence = frame.confidence
                    
                    if confidence >= 0.7:
                        confidence_indicator = "🟢"
                    elif confidence >= 0.5:
                        confidence_indicator = "🟡"
                    else:
                        confidence_indicator = "🔴"
                    
                    print(f"   {confidence_indicator} Frame {i+1}: {time_offset:.1f}s "
                          f"(Confidence: {confidence:.3f})")
                
                if len(label_annotation.frames) > 5:
                    print(f"   ... and {len(label_annotation.frames) - 5} more frames")

    # Summary
    print(f"\n📈 SUMMARY")
    print("=" * 80)
    print(f"Total labels detected: {total_labels}")
    print(f"High confidence labels (≥0.7): {high_confidence_labels}")
    print(f"Success rate: {high_confidence_labels/total_labels*100:.1f}%" if total_labels > 0 else "No labels detected")
    
    return result


def test_video_intelligence_api_with_two_rooms():
    """Test Google Video Intelligence API with two_rooms.mp4 video."""
    
    # Path to the test video
    video_path = Path(__file__).parent / "videos" / "two_rooms.mp4"
    
    assert video_path.exists(), f"Video file not found: {video_path}"
    
    print(f"🎥 Testing Google Video Intelligence API")
    print(f"📁 Video file: {video_path}")
    print(f"📊 Analysis mode: LABEL_DETECTION with SHOT_AND_FRAME_MODE")
    print(f"🔧 Model: builtin/stable")
    
    # Upload video to GCS first
    bucket_name = settings.GCP.Storage.USER_BUCKET  # Use existing bucket
    blob_name = "tests/video-intelligence/two_rooms.mp4"
    
    video_uri = upload_video_to_gcs(
        local_video_path=str(video_path),
        bucket_name=bucket_name,
        blob_name=blob_name
    )
    
    # Analyze the video
    result = analyze_video_with_intelligence(video_uri)
    
    print(f"\n✅ Video Intelligence API test completed successfully!")
    
    # Validate that we got results
    assert result is not None, "Video Intelligence API returned no results"
    assert len(result.annotation_results) > 0, "No annotation results found"
    
    # Save results to JSON file for further analysis
    output_file = Path(__file__).parent / "two_rooms_analysis_results.json"
    
    # Convert result to JSON-serializable format
    results_data = {
        "video_uri": video_uri,
        "analysis_timestamp": str(Path(__file__).stat().st_mtime),
        "segment_labels": [],
        "frame_labels": []
    }
    
    total_labels = 0
    high_confidence_labels = 0
    
    for annotation_result in result.annotation_results:
        # Process segment labels
        for label_annotation in annotation_result.segment_label_annotations:
            total_labels += 1
            label_data = {
                "description": label_annotation.entity.description,
                "entity_id": label_annotation.entity.entity_id,
                "segments": []
            }
            for segment in label_annotation.segments:
                start_time = (segment.segment.start_time_offset.seconds + 
                            segment.segment.start_time_offset.microseconds / 1e6)
                end_time = (segment.segment.end_time_offset.seconds + 
                          segment.segment.end_time_offset.microseconds / 1e6)
                confidence = segment.confidence
                if confidence >= 0.7:
                    high_confidence_labels += 1
                label_data["segments"].append({
                    "start_time": start_time,
                    "end_time": end_time,
                    "confidence": confidence
                })
            results_data["segment_labels"].append(label_data)
        
        # Process frame labels  
        for label_annotation in annotation_result.frame_label_annotations:
            total_labels += 1
            label_data = {
                "description": label_annotation.entity.description,
                "entity_id": label_annotation.entity.entity_id,
                "frames": []
            }
            for frame in label_annotation.frames:
                time_offset = (frame.time_offset.seconds + 
                             frame.time_offset.microseconds / 1e6)
                confidence = frame.confidence
                if confidence >= 0.7:
                    high_confidence_labels += 1
                label_data["frames"].append({
                    "time_offset": time_offset,
                    "confidence": confidence
                })
            results_data["frame_labels"].append(label_data)
    
    with open(output_file, 'w') as f:
        json.dump(results_data, f, indent=2)
    
    print(f"📄 Detailed results saved to: {output_file}")
    
    # Assert that we got meaningful results
    assert total_labels > 0, f"No labels detected in video analysis"
    print(f"📊 Total labels: {total_labels}, High confidence: {high_confidence_labels}")
    
    return results_data


def main():
    """Main function for standalone execution."""
    test_video_intelligence_api_with_two_rooms()


if __name__ == "__main__":
    main()
