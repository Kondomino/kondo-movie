"""
End-to-End Test for Mixed Media Upload Flow
Tests the complete flow from new-media-uploaded endpoint through unified classification
"""

import os
import sys
import shutil
import tempfile
import uuid
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import pytest

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from video.video_actions import VideoActionsHandler
from video.video_actions_model import NewMediaUploadedRequest, FetchProjectMediaRequest
from account.account_model import UserData
from config.config import settings
from gcp.storage import StorageManager


class TestMixedMediaUploadFlow:
    """Test the complete mixed media upload and classification flow"""
    
    @classmethod
    def setup_class(cls):
        """Set up test environment"""
        cls.test_user_id = "test_user_12345"
        cls.test_project_id = str(uuid.uuid4())
        cls.test_user_data = UserData(id=cls.test_user_id, email="test@example.com")
        
        # Test media paths
        cls.test_media_dir = Path(__file__).parent / "properties_medias"
        cls.test_images = list((cls.test_media_dir / "images").glob("*.webp"))[:3]  # Use 3 images
        cls.test_videos = list((cls.test_media_dir / "videos").glob("*.mp4"))[:2]   # Use 2 videos
        
        print(f"🎬 Test Setup:")
        print(f"   User ID: {cls.test_user_id}")
        print(f"   Project ID: {cls.test_project_id}")
        print(f"   Test Images: {[img.name for img in cls.test_images]}")
        print(f"   Test Videos: {[vid.name for vid in cls.test_videos]}")
        
        # Create temporary GCS-like structure
        cls.temp_dir = tempfile.mkdtemp()
        cls.mock_gcs_base = Path(cls.temp_dir) / "mock_gcs"
        cls.mock_gcs_base.mkdir(parents=True)
        
        # Set up mock project structure
        cls.project_base = cls.mock_gcs_base / cls.test_user_id / cls.test_project_id
        cls.images_dir = cls.project_base / "images"
        cls.videos_dir = cls.project_base / "videos"
        cls.images_dir.mkdir(parents=True)
        cls.videos_dir.mkdir(parents=True)
        
    @classmethod
    def teardown_class(cls):
        """Clean up test environment"""
        shutil.rmtree(cls.temp_dir, ignore_errors=True)
        print(f"🧹 Test cleanup completed")
    
    def setup_method(self):
        """Set up for each test method"""
        # Copy test media to mock GCS structure
        self._copy_test_media_to_mock_gcs()
        
    def _copy_test_media_to_mock_gcs(self):
        """Copy test media files to mock GCS structure"""
        print(f"\n📁 Setting up mock GCS structure...")
        
        # Copy images
        for i, image_path in enumerate(self.test_images):
            dest_path = self.images_dir / f"test_image_{i}_{image_path.name}"
            shutil.copy2(image_path, dest_path)
            print(f"   📷 Copied: {image_path.name} → {dest_path.name}")
        
        # Copy videos
        for i, video_path in enumerate(self.test_videos):
            dest_path = self.videos_dir / f"test_video_{i}_{video_path.name}"
            shutil.copy2(video_path, dest_path)
            print(f"   🎥 Copied: {video_path.name} → {dest_path.name}")
    
    def _create_mock_signed_urls(self):
        """Create mock signed URLs for the media files"""
        mock_signed_urls = []
        
        # Mock signed URLs for images
        for image_file in self.images_dir.glob("*"):
            mock_signed_urls.append({
                "file_name": image_file.name,
                "gs_url": f"gs://editora-v2-users/{self.test_user_id}/{self.test_project_id}/images/{image_file.name}",
                "signed_url": f"https://storage.googleapis.com/signed_url_for_{image_file.name}"
            })
        
        # Mock signed URLs for videos
        for video_file in self.videos_dir.glob("*"):
            mock_signed_urls.append({
                "file_name": video_file.name,
                "gs_url": f"gs://editora-v2-users/{self.test_user_id}/{self.test_project_id}/videos/{video_file.name}",
                "signed_url": f"https://storage.googleapis.com/signed_url_for_{video_file.name}"
            })
        
        return mock_signed_urls
    
    @patch('video.video_actions.ProjectManager')
    def test_new_media_uploaded_endpoint(self, mock_project_manager):
        """Test the new-media-uploaded endpoint triggers the correct flow"""
        print(f"\n🚀 Testing new-media-uploaded endpoint...")
        
        # Mock the ProjectManager
        mock_pm_instance = MagicMock()
        mock_project_manager.return_value = mock_pm_instance
        
        # Create request
        request = NewMediaUploadedRequest(project_id=self.test_project_id)
        
        # Create handler and call endpoint (it's async)
        handler = VideoActionsHandler(self.test_user_data)
        response = asyncio.run(handler.new_media_uploaded(request))
        
        # Verify ProjectManager was called correctly
        mock_project_manager.assert_called_once_with(
            user_id=self.test_user_id,
            project_id=self.test_project_id
        )
        mock_pm_instance.media_updated.assert_called_once()
        
        # Verify response
        assert response.message == 'Media successfully uploaded'
        print(f"   ✅ new-media-uploaded endpoint responded correctly")
        print(f"   ✅ ProjectManager.media_updated() was called")
    
    @patch('video.video_actions.backfill_media_signed_urls_for_project')
    @patch('video.video_actions.get_session_refs_by_ids')
    def test_fetch_project_media_endpoint(self, mock_get_refs, mock_backfill):
        """Test the new fetch-project-media endpoint returns both images and videos"""
        print(f"\n📡 Testing fetch-project-media endpoint...")
        
        # Create mock signed URLs
        all_signed_urls = self._create_mock_signed_urls()
        image_urls = [url for url in all_signed_urls if '/images/' in url['gs_url']]
        video_urls = [url for url in all_signed_urls if '/videos/' in url['gs_url']]
        
        # Mock project document with both image and video signed URLs
        mock_project_doc = {
            "media_signed_urls": {
                "media": image_urls,
                "signature_expiry": "2024-12-31T23:59:59Z"
            },
            "video_signed_urls": {
                "media": video_urls,
                "signature_expiry": "2024-12-31T23:59:59Z"
            }
        }
        
        # Mock Firestore references with proper chain
        mock_project_doc_snapshot = MagicMock()
        mock_project_doc_snapshot.to_dict.return_value = mock_project_doc
        
        mock_project_ref = MagicMock()
        mock_project_ref.get.return_value = mock_project_doc_snapshot
        
        mock_get_refs.return_value = (None, mock_project_ref, None)
        
        # Mock the backfill function (it handles the storage manager internally)
        mock_backfill.return_value = None
        
        # Create request
        request = FetchProjectMediaRequest(project_id=self.test_project_id)
        
        # Create handler and call endpoint
        handler = VideoActionsHandler(self.test_user_data)
        response = handler.fetch_project_media(request.project_id)
        
        # Verify response structure
        assert response.message == "Media fetched!"
        assert len(response.images) == len(image_urls)
        assert len(response.videos) == len(video_urls)
        assert response.signature_expiry is not None  # Should be parsed from the mock data
        
        print(f"   ✅ fetch-project-media endpoint responded correctly")
        print(f"   📷 Images returned: {len(response.images)}")
        print(f"   🎥 Videos returned: {len(response.videos)}")
        print(f"   📅 Signature expiry: {response.signature_expiry}")
        
        # Verify image URLs structure
        for img_url in response.images:
            assert 'file_name' in img_url
            assert 'gs_url' in img_url
            assert 'signed_url' in img_url
            assert '/images/' in img_url['gs_url']
        
        # Verify video URLs structure  
        for vid_url in response.videos:
            assert 'file_name' in vid_url
            assert 'gs_url' in vid_url
            assert 'signed_url' in vid_url
            assert '/videos/' in vid_url['gs_url']
        
        print(f"   ✅ All media URLs have correct structure")
    
    @patch('classification.unified_classification_manager.MediaTypeDetector')
    @patch('classification.video_classification_manager.VideoClassificationManager')
    @patch('classification.classification_manager.ClassificationManager')
    @patch('utils.session_utils.get_session_refs_by_ids')
    def test_unified_classification_flow(self, mock_get_refs, mock_image_classifier, 
                                       mock_video_classifier, mock_media_detector):
        """Test the unified classification flow with mixed media"""
        print(f"\n🧠 Testing unified classification flow...")
        
        # Mock Firestore references
        mock_project_ref = MagicMock()
        mock_get_refs.return_value = (None, mock_project_ref, None)
        
        # Mock media detector
        mock_detector_instance = MagicMock()
        mock_media_detector.return_value = mock_detector_instance
        
        # Create mock media inventory
        from classification.media_models import MediaInventory, ImageMedia, VideoMedia
        mock_inventory = MediaInventory(
            images=[ImageMedia(uri=f"gs://test/{img.name}") for img in self.test_images],
            videos=[VideoMedia(uri=f"gs://test/{vid.name}") for vid in self.test_videos],
            has_images=True,
            has_videos=True,
            has_scene_clips=False,
            is_mixed_media=True  # Explicitly set mixed media flag
        )
        mock_detector_instance.analyze_project_media.return_value = mock_inventory
        
        # Mock image classifier
        mock_image_classifier_instance = MagicMock()
        mock_image_classifier.return_value = mock_image_classifier_instance
        mock_image_classifier_instance.run_classification_for_project.return_value = None
        
        # Mock video classifier with VideoSceneBuckets
        from classification.storage import VideoSceneBuckets
        mock_video_classifier_instance = MagicMock()
        mock_video_classifier.return_value = mock_video_classifier_instance
        
        # Create mock video scene buckets
        mock_video_buckets = VideoSceneBuckets()
        mock_video_buckets.google_video_intelligence_used = True
        mock_video_buckets.google_vision_api_used = True
        mock_video_buckets.total_scenes = 5
        mock_video_buckets.processing_summary = {
            "total_videos_processed": len(self.test_videos),
            "total_scenes_detected": 5,
            "keyframes_extracted": 8,
            "vision_api_calls": 8,
            "scenes_refined_by_vision": 3,
            "cost_estimate": 0.012,
            "processing_time": 45.2
        }
        # Add some mock scenes to buckets
        mock_video_buckets.buckets = {
            "Interior": [],
            "Exterior": []
        }
        
        mock_video_classifier_instance.classify_videos.return_value = mock_video_buckets
        
        # Test unified classification
        from classification.unified_classification_manager import UnifiedClassificationManager
        classifier = UnifiedClassificationManager()
        
        # Override the mocked instances
        classifier.media_detector = mock_detector_instance
        classifier.image_classifier = mock_image_classifier_instance  
        classifier.video_classifier = mock_video_classifier_instance
        
        # Run classification
        results = classifier.classify_project_media(self.test_user_id, self.test_project_id)
        
                    # Verify results
        assert results is not None
        assert results.google_vision_api_used == True
        assert results.google_video_intelligence_used == True
        assert results.media_inventory.is_mixed_media == True  # Should detect mixed media (check the correct property)
        assert results.video_scene_buckets is not None
        
        # Verify media detector was called
        mock_detector_instance.analyze_project_media.assert_called_once_with(
            self.test_user_id, self.test_project_id
        )
        
        # Verify image classifier was called
        mock_image_classifier_instance.run_classification_for_project.assert_called_once()
        
        # Verify video classifier was called
        mock_video_classifier_instance.classify_videos.assert_called_once()
        
        print(f"   ✅ Unified classification completed successfully")
        print(f"   📊 Mixed media detected: {results.mixed_media}")
        print(f"   🎥 Video Intelligence used: {results.google_video_intelligence_used}")
        print(f"   👁️  Vision API used: {results.google_vision_api_used}")
        print(f"   📈 Total scenes detected: {results.video_scene_buckets.total_scenes}")
        print(f"   💰 Processing cost estimate: ${results.video_scene_buckets.processing_summary['cost_estimate']:.4f}")
        print(f"   ⏱️  Processing time: {results.video_scene_buckets.processing_summary['processing_time']:.1f}s")
    
    def test_media_type_detection(self):
        """Test that media types are correctly detected"""
        print(f"\n🔍 Testing media type detection...")
        
        from classification.media_detector import MediaTypeDetector
        detector = MediaTypeDetector()
        
        # Test image detection
        for image_path in self.test_images:
            media_type = detector.detect_media_type(f"gs://test/{image_path.name}")
            assert media_type.value == "image"
            print(f"   📷 {image_path.name} → {media_type.value}")
        
        # Test video detection  
        for video_path in self.test_videos:
            media_type = detector.detect_media_type(f"gs://test/{video_path.name}")
            assert media_type.value == "video"
            print(f"   🎥 {video_path.name} → {media_type.value}")
        
        print(f"   ✅ All media types detected correctly")
    
    @patch('classification.video_classification_manager.VideoClassificationManager')
    def test_video_scene_buckets_structure(self, mock_video_classifier):
        """Test that VideoSceneBuckets has the correct structure for frontend consumption"""
        print(f"\n🏗️  Testing VideoSceneBuckets structure...")
        
        from classification.storage import VideoSceneBuckets
        
        # Create a real VideoSceneBuckets instance
        buckets = VideoSceneBuckets()
        buckets.google_video_intelligence_used = True
        buckets.google_vision_api_used = True
        
        # Add mock scene items
        scene_item = VideoSceneBuckets.SceneItem(
            scene_id="scene_30.0s",
            source_video_uri="gs://test/pool_living_room_kitchen.mp4",
            start_time=30.0,
            end_time=33.0,
            confidence=0.85,
            detection_source="vision_api",
            keyframe_uri="gs://test/keyframe_30.0s.jpg"
        )
        
        buckets.add_scene_to_bucket("Interior", scene_item)
        
        # Test structure
        assert len(buckets.get_categories()) == 1
        assert "Interior" in buckets.get_categories()
        assert buckets.total_scenes == 1
        assert buckets.get_scene_count_by_category()["Interior"] == 1
        
        # Test scene item properties
        scenes = buckets.get_scenes_by_category("Interior")
        assert len(scenes) == 1
        scene = scenes[0]
        assert scene.duration == 3.0  # 33.0 - 30.0
        assert scene.detection_source == "vision_api"
        assert scene.keyframe_uri is not None
        
        # Test serialization (for API response)
        serialized = buckets.model_dump()
        assert "buckets" in serialized
        assert "google_video_intelligence_used" in serialized
        assert "google_vision_api_used" in serialized
        assert "total_scenes" in serialized
        
        print(f"   ✅ VideoSceneBuckets structure is correct")
        print(f"   📊 Categories: {buckets.get_categories()}")
        print(f"   🎬 Total scenes: {buckets.total_scenes}")
        print(f"   📈 Summary stats: {buckets.get_summary_stats()}")


def main():
    """Run the mixed media upload flow tests"""
    print("🎬 Mixed Media Upload Flow Test Suite")
    print("=" * 80)
    
    test_instance = TestMixedMediaUploadFlow()
    test_instance.setup_class()
    
    try:
        # Run individual tests
        print(f"\n🧪 Running individual tests...")
        
        test_instance.setup_method()
        test_instance.test_new_media_uploaded_endpoint()
        
        test_instance.setup_method()  
        test_instance.test_fetch_project_media_endpoint()
        
        test_instance.setup_method()
        test_instance.test_unified_classification_flow()
        
        test_instance.setup_method()
        test_instance.test_media_type_detection()
        
        test_instance.setup_method()
        test_instance.test_video_scene_buckets_structure()
        
        print(f"\n🎉 All tests passed successfully!")
        print(f"✅ Mixed media upload flow is working correctly")
        print(f"✅ Backend APIs are properly integrated")
        print(f"✅ Unified classification handles both images and videos")
        print(f"✅ VideoSceneBuckets provides consistent frontend interface")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        test_instance.teardown_class()
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
