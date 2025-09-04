#!/usr/bin/env python3
"""
Test the original API endpoint that was failing
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from property.property_actions import PropertyActionsHandler
from property.property_actions_model import FetchPropertyDetailsRequest
from property.address import Address
from logger import logger

def test_api_endpoint():
    """Test the original API endpoint that was failing"""
    print("🔍 Testing Original API Endpoint")
    print("=" * 50)
    
    # Simulate the original request that was failing
    request = FetchPropertyDetailsRequest(
        property_address="412 N Palm Dr, Beverly Hills, CA 90210, USA",
        property_id="ChIJTW3OEKq-woAR1uTSoW6WteI",
        address_input_type=Address.AddressInputType.AutoComplete,
        project_id="c36a2055-b289-458b-a14f-e5210fb851af"
    )
    
    user_id = "test_user_123"
    
    try:
        handler = PropertyActionsHandler()
        response = handler.fetch_property_details(user_id=user_id, request=request)
        
        print(f"✅ API Endpoint SUCCESS!")
        print(f"   Message: {response.message}")
        print(f"   Property ID: {response.property.get('property_id', 'N/A')}")
        print(f"   Project ID: {response.property.get('project_id', 'N/A')}")
        print(f"   Name: {response.property.get('name', 'N/A')}")
        print(f"   Source: {response.source}")
        print(f"   End Title: {response.property.get('end_title', 'N/A')}")
        print(f"   End Subtitle: {response.property.get('end_subtitle', 'N/A')}")
        script = response.property.get('selected_ai_narration', '')
        print(f"   Script: {script[:100]}..." if script else "No script")
        
    except Exception as e:
        print(f"❌ API Endpoint FAILED: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_endpoint()
    print("=" * 50)
    print("🏁 API Test complete!") 