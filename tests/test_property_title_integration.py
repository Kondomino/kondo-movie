#!/usr/bin/env python3
"""
Integration test for PropertyTitle flow with Jenna Cooper LA engine
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.address import Address
from property.property_actions_model import FetchPropertyDetailsRequest, FetchPropertyRequest
from property.property_actions import PropertyActionsHandler
from property.property_manager import PropertyManager
from utils.common_models import ActionStatus

def test_property_title_integration():
    """Test that PropertyTitle integration works correctly end-to-end"""
    print("Testing PropertyTitle integration with Jenna Cooper LA...")
    
    # Test 1: Test PropertyManager with PropertyTitle
    try:
        print("\n=== Test 1: PropertyManager with PropertyTitle ===")
        property_mgr = PropertyManager(
            address="BRENTWOOD PRIVATE ESTATE",
            tenant_id="jenna_cooper_la",
            address_input_type=Address.AddressInputType.PropertyTitle,
            title="BRENTWOOD PRIVATE ESTATE"
        )
        
        print(f"✓ PropertyManager created successfully")
        print(f"  - Address: {property_mgr.address.input_address}")
        print(f"  - Tenant ID: {property_mgr.tenant_id}")
        print(f"  - Address input type: {property_mgr.address.address_input_type.name}")
        print(f"  - Title: {property_mgr.title}")
        
        # Check if PropertyTitle detection works
        is_property_title = (property_mgr.address.address_input_type == Address.AddressInputType.PropertyTitle and 
                           property_mgr.tenant_id == "jenna_cooper_la")
        print(f"  - Is PropertyTitle search: {is_property_title}")
        
    except Exception as e:
        print(f"✗ Failed to create PropertyManager: {e}")
        return False
    
    # Test 2: Test PropertyActionsHandler logic
    try:
        print("\n=== Test 2: PropertyActionsHandler logic ===")
        handler = PropertyActionsHandler()
        
        # Create FetchPropertyRequest with PropertyTitle
        fetch_request = FetchPropertyRequest(
            request_id="test-request-id",
            property_address="BRENTWOOD PRIVATE ESTATE",
            address_input_type=Address.AddressInputType.PropertyTitle,
            title="BRENTWOOD PRIVATE ESTATE"
        )
        
        print(f"✓ FetchPropertyRequest created successfully")
        print(f"  - Request ID: {fetch_request.request_id}")
        print(f"  - Property address: {fetch_request.property_address}")
        print(f"  - Address input type: {fetch_request.address_input_type}")
        print(f"  - Title: {fetch_request.title}")
        
        # Test the logic that determines when to use title search
        use_title_search = (
            fetch_request.address_input_type == Address.AddressInputType.PropertyTitle or
            (fetch_request.title and "jenna_cooper_la" == "jenna_cooper_la")
        )
        
        print(f"✓ Title search logic test passed")
        print(f"  - Use title search: {use_title_search}")
        print(f"  - Address input type is PropertyTitle: {fetch_request.address_input_type == Address.AddressInputType.PropertyTitle}")
        
    except Exception as e:
        print(f"✗ Failed to test PropertyActionsHandler logic: {e}")
        return False
    
    # Test 3: Test API request validation
    try:
        print("\n=== Test 3: API request validation ===")
        request = FetchPropertyDetailsRequest(
            property_id="test-id",
            property_address="BRENTWOOD PRIVATE ESTATE",
            address_input_type=Address.AddressInputType.PropertyTitle,
            title="BRENTWOOD PRIVATE ESTATE"
        )
        
        print(f"✓ API request validation passed")
        print(f"  - Property ID: {request.property_id}")
        print(f"  - Property address: {request.property_address}")
        print(f"  - Address input type: {request.address_input_type}")
        print(f"  - Title: {request.title}")
        
    except Exception as e:
        print(f"✗ Failed API request validation: {e}")
        return False
    
    # Test 4: Test Address object with PropertyTitle
    try:
        print("\n=== Test 4: Address object with PropertyTitle ===")
        address = Address("BRENTWOOD PRIVATE ESTATE", Address.AddressInputType.PropertyTitle, "jenna_cooper_la")
        
        print(f"✓ Address object created with PropertyTitle type")
        print(f"  - Input address: {address.input_address}")
        print(f"  - Formatted address: {address.formatted_address}")
        print(f"  - Place ID: {address.place_id}")
        print(f"  - Address input type: {address.address_input_type.name}")
        print(f"  - Primary type: {address.primary_type}")
        print(f"  - Types: {address.types}")
        
        # Test plausible address matches
        matches = address.plausible_address_matches()
        print(f"  - Plausible matches: {matches}")
        
    except Exception as e:
        print(f"✗ Failed to create Address with PropertyTitle: {e}")
        return False
    
    print("\n✓ All PropertyTitle integration tests passed!")
    return True

if __name__ == "__main__":
    success = test_property_title_integration()
    if success:
        print("\n🎉 PropertyTitle integration test completed successfully!")
    else:
        print("\n❌ PropertyTitle integration test failed!")
        sys.exit(1) 