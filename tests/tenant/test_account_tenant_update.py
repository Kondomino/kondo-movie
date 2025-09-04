import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from src.main import app
from src.account.account_model import UserData, UserInfo

client = TestClient(app)

@pytest.fixture
def mock_user_data():
    return UserData(
        id="test_user_123",
        user_info=UserInfo(
            email="test@example.com",
            first_name="Test",
            last_name="User"
        ),
        tenant_id="editora"
    )

@pytest.fixture
def mock_authenticate(mock_user_data):
    with patch('src.account.authentication.authenticate') as mock_auth:
        mock_auth.return_value = mock_user_data
        yield mock_auth

def test_update_user_tenant_success(mock_authenticate):
    """Test successful tenant update"""
    user_id = "test_user_123"
    new_tenant_id = "new_tenant_456"
    
    with patch('src.account.account_actions.db_client') as mock_db:
        # Mock the user document
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "id": user_id,
            "user_info": {
                "email": "test@example.com",
                "first_name": "Test",
                "last_name": "User"
            },
            "tenant_id": "editora"
        }
        
        mock_ref = Mock()
        mock_ref.get.return_value = mock_doc
        mock_ref.update = Mock()
        
        mock_collection = Mock()
        mock_collection.document.return_value = mock_ref
        mock_db.collection.return_value = mock_collection
        
        # Mock tenant utils
        with patch('src.account.account_actions.get_tenant_info') as mock_tenant:
            mock_tenant.return_value = Mock(
                id=new_tenant_id,
                name="New Tenant",
                url="https://newtenant.com"
            )
            
            response = client.patch(
                f"/api/v1/update-tenant/{user_id}",
                json={"tenant_id": new_tenant_id},
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == f"User tenant updated successfully for ID '{user_id}'"
            assert "user_data" in data
            assert data["user_data"]["tenant_id"] == new_tenant_id
            assert "tenant" in data["user_data"]
            assert data["user_data"]["tenant"]["id"] == new_tenant_id

def test_update_user_tenant_user_not_found(mock_authenticate):
    """Test tenant update when user doesn't exist"""
    user_id = "nonexistent_user"
    new_tenant_id = "new_tenant_456"
    
    with patch('src.account.account_actions.db_client') as mock_db:
        # Mock the user document as not existing
        mock_doc = Mock()
        mock_doc.exists = False
        
        mock_ref = Mock()
        mock_ref.get.return_value = mock_doc
        
        mock_collection = Mock()
        mock_collection.document.return_value = mock_ref
        mock_db.collection.return_value = mock_collection
        
        response = client.patch(
            f"/api/v1/update-tenant/{user_id}",
            json={"tenant_id": new_tenant_id},
            headers={"Authorization": "Bearer test_token"}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert f"User with ID '{user_id}' not found" in data["detail"]

if __name__ == "__main__":
    pytest.main([__file__]) 