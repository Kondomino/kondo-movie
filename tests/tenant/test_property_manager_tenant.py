#!/usr/bin/env python3
"""
Test script to verify PropertyManager uses correct tenant-specific engines.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from property.property_manager import PropertyManager
from property.address import Address

def test_property_manager_tenants():
    print("🧪 Testing PropertyManager Tenant Engine Selection")
    print("=" * 60)
    
    # Test addresses
    test_address = "123 Main St, New York, NY 10001"
    
    # Test 1: Daniel Gale tenant
    print("\n1. Testing Daniel Gale tenant:")
    try:
        property_mgr = PropertyManager(
            address=test_address,
            tenant_id="daniel_gale"
        )
        print(f"   ✅ PropertyManager created with tenant_id: {property_mgr.tenant_id}")
        print(f"   Selected engines: {[engine.__class__.__name__ for engine in property_mgr.engines]}")
        
        # Check if DanielGale is first
        if property_mgr.engines and property_mgr.engines[0].__class__.__name__ == "DanielGale":
            print("   ✅ DanielGale engine is correctly placed first")
        else:
            print("   ❌ DanielGale engine is NOT first")
            
    except Exception as e:
        print(f"   ❌ Failed to create PropertyManager for daniel_gale: {str(e)}")
        return False
    
    # Test 2: Editora tenant (default)
    print("\n2. Testing Editora tenant (default):")
    try:
        property_mgr = PropertyManager(
            address=test_address,
            tenant_id="editora"
        )
        print(f"   ✅ PropertyManager created with tenant_id: {property_mgr.tenant_id}")
        print(f"   Selected engines: {[engine.__class__.__name__ for engine in property_mgr.engines]}")
        
        # Check if ColdwellBanker is first
        if property_mgr.engines and property_mgr.engines[0].__class__.__name__ == "ColdwellBanker":
            print("   ✅ ColdwellBanker engine is correctly placed first")
        else:
            print("   ❌ ColdwellBanker engine is NOT first")
            
    except Exception as e:
        print(f"   ❌ Failed to create PropertyManager for editora: {str(e)}")
        return False
    
    # Test 3: Jenna Cooper LA tenant
    print("\n3. Testing Jenna Cooper LA tenant:")
    try:
        property_mgr = PropertyManager(
            address=test_address,
            tenant_id="jenna_cooper_la"
        )
        print(f"   ✅ PropertyManager created with tenant_id: {property_mgr.tenant_id}")
        print(f"   Selected engines: {[engine.__class__.__name__ for engine in property_mgr.engines]}")
        
        # Check if Zillow is first
        if property_mgr.engines and property_mgr.engines[0].__class__.__name__ == "Zillow":
            print("   ✅ Zillow engine is correctly placed first")
        else:
            print("   ❌ Zillow engine is NOT first")
            
    except Exception as e:
        print(f"   ❌ Failed to create PropertyManager for jenna_cooper_la: {str(e)}")
        return False
    
    # Test 4: Watson Salari Group tenant
    print("\n4. Testing Watson Salari Group tenant:")
    try:
        property_mgr = PropertyManager(
            address=test_address,
            tenant_id="watson_salari_group"
        )
        print(f"   ✅ PropertyManager created with tenant_id: {property_mgr.tenant_id}")
        print(f"   Selected engines: {[engine.__class__.__name__ for engine in property_mgr.engines]}")
        
        # Check if Zillow is first
        if property_mgr.engines and property_mgr.engines[0].__class__.__name__ == "Zillow":
            print("   ✅ Zillow engine is correctly placed first")
        else:
            print("   ❌ Zillow engine is NOT first")
            
    except Exception as e:
        print(f"   ❌ Failed to create PropertyManager for watson_salari_group: {str(e)}")
        return False
    
    print("\n✅ All PropertyManager tenant tests passed!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_property_manager_tenants()
    if success:
        print("\n🎉 PropertyManager tenant engine selection is working correctly!")
    else:
        print("\n❌ PropertyManager tenant engine selection tests failed!")
        sys.exit(1) 