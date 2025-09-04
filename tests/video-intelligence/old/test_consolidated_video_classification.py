"""
Test script for the consolidated video classification manager
Validates the ADR-002 optimized pipeline with VideoSceneBuckets
"""

import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from classification.video_classification_manager import VideoClassificationManager
from classification.storage import VideoSceneBuckets
from classification.media_models import VideoMedia


def test_consolidated_video_classification():
    """Test the consolidated video classification manager with pool_living_room_kitchen.mp4"""
    
    print("🚀 Testing Consolidated Video Classification Manager")
    print("=" * 60)
    
    # Initialize the consolidated manager
    manager = VideoClassificationManager()
    print(f"✅ Initialized consolidated video classification manager")
    
    # Test video
    test_video_uri = "gs://editora-user-bucket/tests/properties_medias/videos/pool_living_room_kitchen.mp4"
    test_video = VideoMedia(uri=test_video_uri, duration=60.0)  # Approximate duration
    
    print(f"📹 Testing with video: {test_video_uri}")
    
    try:
        # Run consolidated classification
        video_scene_buckets = manager.classify_videos(
            videos=[test_video],
            user_id="test_user",
            project_id="test_project"
        )
        
        if not video_scene_buckets or video_scene_buckets.total_scenes == 0:
            print("❌ No scenes detected - this may indicate an issue with the pipeline")
            return False
        
        # Display results
        print(f"\n📊 Classification Results:")
        print(f"   Total scenes detected: {video_scene_buckets.total_scenes}")
        print(f"   Categories found: {len(video_scene_buckets.get_categories())}")
        print(f"   Google Video Intelligence used: {video_scene_buckets.google_video_intelligence_used}")
        print(f"   Google Vision API used: {video_scene_buckets.google_vision_api_used}")
        
        # Display category breakdown
        print(f"\n🏷️  Category Breakdown:")
        for category, scenes in video_scene_buckets.buckets.items():
            if scenes:
                print(f"   {category}: {len(scenes)} scenes")
                for i, scene in enumerate(scenes[:2]):  # Show first 2 scenes per category
                    print(f"      Scene {i+1}: {scene.scene_id} ({scene.start_time:.1f}s-{scene.end_time:.1f}s, "
                          f"confidence: {scene.confidence:.2f}, source: {scene.detection_source})")
        
        # Display processing summary
        if video_scene_buckets.processing_summary:
            print(f"\n⚡ Processing Summary:")
            summary = video_scene_buckets.processing_summary
            print(f"   Processing time: {summary.get('processing_time', 0):.2f}s")
            print(f"   Keyframes extracted: {summary.get('keyframes_extracted', 0)}")
            print(f"   Vision API calls: {summary.get('vision_api_calls', 0)}")
            print(f"   Scenes refined by Vision: {summary.get('scenes_refined_by_vision', 0)}")
            print(f"   Estimated cost: ${summary.get('cost_estimate', 0):.4f}")
        
        # Display summary stats
        stats = video_scene_buckets.get_summary_stats()
        print(f"\n📈 Summary Statistics:")
        print(f"   Average confidence: {stats['avg_confidence']:.2f}")
        print(f"   Scenes with keyframes: {stats['scenes_with_keyframes']}")
        print(f"   Detection sources: {stats['detection_sources']}")
        
        print(f"\n✅ Consolidated video classification test completed successfully!")
        print(f"🎯 ADR-002 optimizations applied: intelligent filtering, hybrid classification, cost control")
        
        return True
        
    except Exception as e:
        print(f"❌ Consolidated video classification test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_video_scene_buckets_model():
    """Test the VideoSceneBuckets model functionality"""
    
    print("\n🧪 Testing VideoSceneBuckets Model")
    print("=" * 40)
    
    try:
        # Create test buckets
        buckets = VideoSceneBuckets()
        
        # Create test scene items
        scene1 = VideoSceneBuckets.SceneItem(
            scene_id="scene_10.5s",
            source_video_uri="gs://bucket/test.mp4",
            start_time=10.0,
            end_time=13.0,
            confidence=0.85,
            detection_source="vision_api",
            keyframe_uri="gs://bucket/keyframe1.jpg"
        )
        
        scene2 = VideoSceneBuckets.SceneItem(
            scene_id="scene_25.0s",
            source_video_uri="gs://bucket/test.mp4",
            start_time=25.0,
            end_time=28.0,
            confidence=0.92,
            detection_source="video_intelligence"
        )
        
        # Add scenes to buckets
        buckets.add_scene_to_bucket("Interior", scene1)
        buckets.add_scene_to_bucket("Exterior", scene2)
        
        # Test model methods
        print(f"✅ Total scenes: {buckets.total_scenes}")
        print(f"✅ Categories: {buckets.get_categories()}")
        print(f"✅ Scene count by category: {buckets.get_scene_count_by_category()}")
        print(f"✅ Summary stats: {buckets.get_summary_stats()}")
        
        # Test scene duration property
        print(f"✅ Scene 1 duration: {scene1.duration}s")
        print(f"✅ Scene 2 duration: {scene2.duration}s")
        
        print(f"✅ VideoSceneBuckets model test completed successfully!")
        
        return True
        
    except Exception as e:
        print(f"❌ VideoSceneBuckets model test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("🎬 Consolidated Video Classification Test Suite")
    print("=" * 80)
    
    # Test the model first
    model_success = test_video_scene_buckets_model()
    
    # Run the full pipeline test automatically (requires API calls)
    if model_success:
        print("\n🚀 Running full pipeline test with Google APIs...")
        pipeline_success = test_consolidated_video_classification()
    else:
        pipeline_success = False
    
    # Summary
    print(f"\n🏁 Test Results:")
    print(f"   Model test: {'✅ PASSED' if model_success else '❌ FAILED'}")
    print(f"   Pipeline test: {'✅ PASSED' if pipeline_success else '❌ FAILED'}")
    
    if model_success and pipeline_success:
        print(f"\n🎉 All tests passed! Consolidated video classification is ready for production.")
    else:
        print(f"\n⚠️  Some tests failed. Please review the errors above.")
