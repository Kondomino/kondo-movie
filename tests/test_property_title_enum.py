#!/usr/bin/env python3
"""
Test for PropertyTitle enum value in Address class
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.address import Address
from property.property_actions_model import FetchPropertyDetailsRequest
from pydantic import ValidationError

def test_property_title_enum():
    """Test that PropertyTitle enum works correctly"""
    print("Testing PropertyTitle enum...")
    
    # Test 1: Create Address with PropertyTitle type
    try:
        address = Address("BRENTWOOD PRIVATE ESTATE", Address.AddressInputType.PropertyTitle)
        print(f"✓ Address created successfully with PropertyTitle type")
        print(f"  - Input address: {address.input_address}")
        print(f"  - Formatted address: {address.formatted_address}")
        print(f"  - Place ID: {address.place_id}")
        print(f"  - Address input type: {address.address_input_type.name}")
        print(f"  - Primary type: {address.primary_type}")
        print(f"  - Types: {address.types}")
    except Exception as e:
        print(f"✗ Failed to create Address with PropertyTitle: {e}")
        return False
    
    # Test 2: Test API request validation
    try:
        request = FetchPropertyDetailsRequest(
            property_id="test-id",
            property_address="BRENTWOOD PRIVATE ESTATE",
            address_input_type=Address.AddressInputType.PropertyTitle,
            title="BRENTWOOD PRIVATE ESTATE"
        )
        print(f"✓ API request validation passed with PropertyTitle")
        print(f"  - Property address: {request.property_address}")
        print(f"  - Address input type: {request.address_input_type}")
        print(f"  - Title: {request.title}")
    except ValidationError as e:
        print(f"✗ API request validation failed: {e}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error in API request validation: {e}")
        return False
    
    # Test 3: Test plausible address matches
    try:
        matches = address.plausible_address_matches()
        print(f"✓ Plausible address matches generated: {matches}")
    except Exception as e:
        print(f"✗ Failed to generate plausible address matches: {e}")
        return False
    
    print("✓ All PropertyTitle enum tests passed!")
    return True

if __name__ == "__main__":
    success = test_property_title_enum()
    if success:
        print("\n🎉 PropertyTitle enum test completed successfully!")
    else:
        print("\n❌ PropertyTitle enum test failed!")
        sys.exit(1) 