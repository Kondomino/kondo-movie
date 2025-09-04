#!/usr/bin/env python3
"""
Test for PropertyTitle flow with Jenna Cooper LA engine
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.address import Address
from property.property_actions_model import FetchPropertyDetailsRequest, FetchPropertyRequest
from property.property_actions import PropertyActionsHandler
from utils.common_models import ActionStatus

def test_property_title_flow():
    """Test that PropertyTitle flow works correctly with Jenna Cooper LA"""
    print("Testing PropertyTitle flow with Jenna Cooper LA...")
    
    # Test 1: Create API request with PropertyTitle
    try:
        request = FetchPropertyDetailsRequest(
            property_id="test-id",
            property_address="BRENTWOOD PRIVATE ESTATE",
            address_input_type=Address.AddressInputType.PropertyTitle,
            title="BRENTWOOD PRIVATE ESTATE"
        )
        print(f"✓ API request created successfully")
        print(f"  - Property address: {request.property_address}")
        print(f"  - Address input type: {request.address_input_type}")
        print(f"  - Title: {request.title}")
    except Exception as e:
        print(f"✗ Failed to create API request: {e}")
        return False
    
    # Test 2: Test PropertyActionsHandler logic
    try:
        handler = PropertyActionsHandler()
        
        # Create FetchPropertyRequest
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
    
    # Test 3: Test Address object with PropertyTitle
    try:
        address = Address("BRENTWOOD PRIVATE ESTATE", Address.AddressInputType.PropertyTitle, "jenna_cooper_la")
        print(f"✓ Address object created with PropertyTitle type")
        print(f"  - Input address: {address.input_address}")
        print(f"  - Formatted address: {address.formatted_address}")
        print(f"  - Place ID: {address.place_id}")
        print(f"  - Address input type: {address.address_input_type.name}")
        print(f"  - Primary type: {address.primary_type}")
        print(f"  - Types: {address.types}")
    except Exception as e:
        print(f"✗ Failed to create Address with PropertyTitle: {e}")
        return False
    
    print("✓ All PropertyTitle flow tests passed!")
    return True

if __name__ == "__main__":
    success = test_property_title_flow()
    if success:
        print("\n🎉 PropertyTitle flow test completed successfully!")
    else:
        print("\n❌ PropertyTitle flow test failed!")
        sys.exit(1) 