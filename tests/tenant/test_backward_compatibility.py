#!/usr/bin/env python3
"""
Test script to verify backward compatibility for users without tenant_id.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from account.account_model import UserData, UserInfo
from utils.tenant_utils import get_tenant_info, get_tenant_name, get_tenant_url
from config.config import settings

def test_backward_compatibility():
    print("🧪 Testing Tenant System Backward Compatibility")
    print("=" * 60)
    
    # Test 1: User with no tenant_id (old user format)
    print("\n1. Testing user with NO tenant_id (old format):")
    try:
        old_user = UserData(
            id="old_user_123",
            user_info=UserInfo(email="old@example.com", first_name="Old", last_name="User")
            # No tenant_id specified - should use default
        )
        print(f"   ✅ Created old user: {old_user.user_info.first_name} {old_user.user_info.last_name}")
        print(f"   User ID: {old_user.id}")
        print(f"   Tenant ID: {getattr(old_user, 'tenant_id', 'NOT SET')}")
        
        # Test tenant functions
        tenant_info = get_tenant_info(old_user)
        tenant_name = get_tenant_name(old_user)
        tenant_url = get_tenant_url(old_user)
        
        print(f"   ✅ Tenant info retrieved: {tenant_info is not None}")
        print(f"   Tenant name: {tenant_name}")
        print(f"   Tenant URL: {tenant_url}")
        
    except Exception as e:
        print(f"   ❌ Failed to handle old user format: {str(e)}")
        return False
    
    # Test 2: User with tenant_id (new user format)
    print("\n2. Testing user WITH tenant_id (new format):")
    try:
        new_user = UserData(
            id="new_user_456",
            user_info=UserInfo(email="new@example.com", first_name="New", last_name="User"),
            tenant_id="editora"  # Explicit tenant_id
        )
        print(f"   ✅ Created new user: {new_user.user_info.first_name} {new_user.user_info.last_name}")
        print(f"   User ID: {new_user.id}")
        print(f"   Tenant ID: {new_user.tenant_id}")
        
        # Test tenant functions
        tenant_info = get_tenant_info(new_user)
        tenant_name = get_tenant_name(new_user)
        tenant_url = get_tenant_url(new_user)
        
        print(f"   ✅ Tenant info retrieved: {tenant_info is not None}")
        print(f"   Tenant name: {tenant_name}")
        print(f"   Tenant URL: {tenant_url}")
        
    except Exception as e:
        print(f"   ❌ Failed to handle new user format: {str(e)}")
        return False
    
    # Test 3: User with None tenant_id (explicit None)
    print("\n3. Testing user with explicit None tenant_id:")
    try:
        none_user = UserData(
            id="none_user_789",
            user_info=UserInfo(email="none@example.com", first_name="None", last_name="User"),
            tenant_id=None  # Explicit None
        )
        print(f"   ✅ Created user with None tenant_id: {none_user.user_info.first_name} {none_user.user_info.last_name}")
        print(f"   User ID: {none_user.id}")
        print(f"   Tenant ID: {none_user.tenant_id}")
        
        # Test tenant functions
        tenant_info = get_tenant_info(none_user)
        tenant_name = get_tenant_name(none_user)
        tenant_url = get_tenant_url(none_user)
        
        print(f"   ✅ Tenant info retrieved: {tenant_info is not None}")
        print(f"   Tenant name: {tenant_name}")
        print(f"   Tenant URL: {tenant_url}")
        
    except Exception as e:
        print(f"   ❌ Failed to handle None tenant_id: {str(e)}")
        return False
    
    # Test 4: Test default tenant configuration
    print("\n4. Testing default tenant configuration:")
    try:
        default_tenant_id = settings.Tenants.DEFAULT_TENANT_ID
        print(f"   Default tenant ID: {default_tenant_id}")
        
        tenants_dict = settings.Tenants.TENANTS.model_dump()
        default_tenant = tenants_dict.get(default_tenant_id)
        if default_tenant:
            print(f"   Default tenant name: {default_tenant.get('name')}")
            print(f"   Default tenant URL: {default_tenant.get('url')}")
        else:
            print(f"   ❌ Default tenant not found in configuration")
            return False
            
    except Exception as e:
        print(f"   ❌ Failed to access default tenant configuration: {str(e)}")
        return False
    
    print("\n✅ All backward compatibility tests passed!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_backward_compatibility()
    if success:
        print("\n🎉 Backward compatibility is working correctly!")
    else:
        print("\n❌ Backward compatibility tests failed!")
        sys.exit(1) 