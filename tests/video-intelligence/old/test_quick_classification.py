"""
Quick test for video classification - always runs the full pipeline
"""

import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from classification.video_classification_manager import VideoClassificationManager
from classification.media_models import VideoMedia


def main():
    """Quick test of video classification with pool_living_room_kitchen.mp4"""
    
    print("🎬 Quick Video Classification Test")
    print("=" * 50)
    
    # Initialize the manager
    manager = VideoClassificationManager()
    print(f"✅ Video classification manager initialized")
    
    # Test with the complex video
    test_video_uri = "gs://editora-user-bucket/tests/properties_medias/videos/pool_living_room_kitchen.mp4"
    test_video = VideoMedia(uri=test_video_uri, duration=60.0)
    
    print(f"📹 Classifying video: pool_living_room_kitchen.mp4")
    print(f"🔗 URI: {test_video_uri}")
    
    try:
        # Run classification
        print(f"\n⚡ Starting classification (this will take ~30-60 seconds)...")
        video_scene_buckets = manager.classify_videos(
            videos=[test_video],
            user_id="test_user",
            project_id="test_project"
        )
        
        if not video_scene_buckets or video_scene_buckets.total_scenes == 0:
            print("❌ No scenes detected!")
            return
        
        # Show results
        print(f"\n🎉 Classification Complete!")
        print(f"📊 Total scenes: {video_scene_buckets.total_scenes}")
        print(f"🏷️  Categories: {len(video_scene_buckets.get_categories())}")
        
        # Show each category
        print(f"\n📋 Scene Breakdown:")
        for category, scenes in video_scene_buckets.buckets.items():
            if scenes:
                print(f"\n  🏠 {category.upper()} ({len(scenes)} scenes):")
                for scene in scenes:
                    print(f"     • {scene.scene_id}: {scene.start_time:.1f}s-{scene.end_time:.1f}s "
                          f"(confidence: {scene.confidence:.2f}, source: {scene.detection_source})")
                    if scene.keyframe_uri:
                        print(f"       🖼️  Keyframe: {scene.keyframe_uri.split('/')[-1]}")
        
        # Show processing summary
        if video_scene_buckets.processing_summary:
            summary = video_scene_buckets.processing_summary
            print(f"\n⚡ Processing Summary:")
            print(f"   ⏱️  Time: {summary.get('processing_time', 0):.1f}s")
            print(f"   🖼️  Keyframes: {summary.get('keyframes_extracted', 0)}")
            print(f"   👁️  Vision API calls: {summary.get('vision_api_calls', 0)}")
            print(f"   🎯 Scenes refined: {summary.get('scenes_refined_by_vision', 0)}")
            print(f"   💰 Cost: ${summary.get('cost_estimate', 0):.4f}")
        
        print(f"\n✅ Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
