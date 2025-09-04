"""
Test for signature_expiry validation fix
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from video.video_actions import VideoActionsHandler
from video.video_actions_model import FetchProjectMediaRequest
from account.account_model import UserData


def test_signature_expiry_empty_string_handling():
    """Test that empty signature_expiry string is properly handled"""
    
    test_user_data = UserData(id="test_user", email="test@example.com")
    test_project_id = "test_project_123"
    
    with patch('video.video_actions.backfill_media_signed_urls_for_project') as mock_backfill, \
         patch('video.video_actions.get_session_refs_by_ids') as mock_get_refs:
        
        # Mock project document with EMPTY signature_expiry (the problematic case)
        mock_project_doc = {
            "media_signed_urls": {
                "media": [{"file_name": "test.jpg", "gs_url": "gs://test", "signed_url": "https://test"}],
                "signature_expiry": ""  # This was causing the validation error
            },
            "video_signed_urls": {
                "media": [{"file_name": "test.mp4", "gs_url": "gs://test", "signed_url": "https://test"}],
                "signature_expiry": ""
            }
        }
        
        # Set up mocks
        mock_project_doc_snapshot = MagicMock()
        mock_project_doc_snapshot.to_dict.return_value = mock_project_doc
        
        mock_project_ref = MagicMock()
        mock_project_ref.get.return_value = mock_project_doc_snapshot
        
        mock_get_refs.return_value = (None, mock_project_ref, None)
        mock_backfill.return_value = None
        
        # Test the endpoint
        handler = VideoActionsHandler(test_user_data)
        response = handler.fetch_project_media(test_project_id)
        
        # Verify it works without validation error
        assert response.message == "Media fetched!"
        assert response.signature_expiry is None  # Should be None instead of empty string
        assert len(response.images) == 1
        assert len(response.videos) == 1
        
        print("✅ Empty signature_expiry string properly handled")


def test_signature_expiry_valid_datetime_handling():
    """Test that valid datetime signature_expiry is properly handled"""
    
    test_user_data = UserData(id="test_user", email="test@example.com")
    test_project_id = "test_project_123"
    
    with patch('video.video_actions.backfill_media_signed_urls_for_project') as mock_backfill, \
         patch('video.video_actions.get_session_refs_by_ids') as mock_get_refs:
        
        # Mock project document with VALID signature_expiry
        valid_expiry = "2024-12-31T23:59:59Z"
        mock_project_doc = {
            "media_signed_urls": {
                "media": [{"file_name": "test.jpg", "gs_url": "gs://test", "signed_url": "https://test"}],
                "signature_expiry": valid_expiry
            },
            "video_signed_urls": {
                "media": [{"file_name": "test.mp4", "gs_url": "gs://test", "signed_url": "https://test"}],
                "signature_expiry": valid_expiry
            }
        }
        
        # Set up mocks
        mock_project_doc_snapshot = MagicMock()
        mock_project_doc_snapshot.to_dict.return_value = mock_project_doc
        
        mock_project_ref = MagicMock()
        mock_project_ref.get.return_value = mock_project_doc_snapshot
        
        mock_get_refs.return_value = (None, mock_project_ref, None)
        mock_backfill.return_value = None
        
        # Test the endpoint
        handler = VideoActionsHandler(test_user_data)
        response = handler.fetch_project_media(test_project_id)
        
        # Verify it works with valid datetime
        assert response.message == "Media fetched!"
        assert response.signature_expiry is not None  # Should be parsed datetime
        assert len(response.images) == 1
        assert len(response.videos) == 1
        
        print(f"✅ Valid signature_expiry datetime properly parsed: {response.signature_expiry}")


def test_signature_expiry_missing_field_handling():
    """Test that missing signature_expiry field is properly handled"""
    
    test_user_data = UserData(id="test_user", email="test@example.com")
    test_project_id = "test_project_123"
    
    with patch('video.video_actions.backfill_media_signed_urls_for_project') as mock_backfill, \
         patch('video.video_actions.get_session_refs_by_ids') as mock_get_refs:
        
        # Mock project document with NO signature_expiry field
        mock_project_doc = {
            "media_signed_urls": {
                "media": [{"file_name": "test.jpg", "gs_url": "gs://test", "signed_url": "https://test"}]
                # No signature_expiry field at all
            },
            "video_signed_urls": {
                "media": [{"file_name": "test.mp4", "gs_url": "gs://test", "signed_url": "https://test"}]
            }
        }
        
        # Set up mocks
        mock_project_doc_snapshot = MagicMock()
        mock_project_doc_snapshot.to_dict.return_value = mock_project_doc
        
        mock_project_ref = MagicMock()
        mock_project_ref.get.return_value = mock_project_doc_snapshot
        
        mock_get_refs.return_value = (None, mock_project_ref, None)
        mock_backfill.return_value = None
        
        # Test the endpoint
        handler = VideoActionsHandler(test_user_data)
        response = handler.fetch_project_media(test_project_id)
        
        # Verify it works without signature_expiry field
        assert response.message == "Media fetched!"
        assert response.signature_expiry is None  # Should be None when missing
        assert len(response.images) == 1
        assert len(response.videos) == 1
        
        print("✅ Missing signature_expiry field properly handled")


if __name__ == "__main__":
    print("🧪 Testing signature_expiry validation fixes...")
    
    test_signature_expiry_empty_string_handling()
    test_signature_expiry_valid_datetime_handling()
    test_signature_expiry_missing_field_handling()
    
    print("\n🎉 All signature_expiry tests passed!")
    print("✅ The production validation error should now be fixed")
