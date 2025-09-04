#!/usr/bin/env python3
"""
Test script to verify the tenant system implementation.
"""

from src.account.account_model import UserData, UserInfo
from src.utils.tenant_utils import get_tenant_info, get_tenant_name, get_tenant_url, get_tenant_by_id, get_all_tenants
from src.config.config import settings

def test_tenant_system():
    print("🧪 Testing Tenant System Implementation")
    print("=" * 50)
    
    # Test 1: Create user with default tenant
    print("\n1. Testing user with default tenant (editora):")
    user_editora = UserData(
        id="user-1",
        user_info=UserInfo(email="user1@editora.ai", first_name="John", last_name="Doe"),
        tenant_id="editora"
    )
    print(f"   User: {user_editora.user_info.first_name} {user_editora.user_info.last_name}")
    print(f"   Tenant ID: {user_editora.tenant_id}")
    
    tenant_info = get_tenant_info(user_editora)
    print(f"   Tenant Name: {tenant_info.name}")
    print(f"   Tenant URL: {tenant_info.url}")
    
    # Test 2: Create user with company_a tenant
    print("\n2. Testing user with company_a tenant:")
    user_company_a = UserData(
        id="user-2", 
        user_info=UserInfo(email="user2@company-a.com", first_name="Jane", last_name="Smith"),
        tenant_id="company_a"
    )
    print(f"   User: {user_company_a.user_info.first_name} {user_company_a.user_info.last_name}")
    print(f"   Tenant ID: {user_company_a.tenant_id}")
    
    tenant_info = get_tenant_info(user_company_a)
    print(f"   Tenant Name: {tenant_info.name}")
    print(f"   Tenant URL: {tenant_info.url}")
    
    # Test 3: Test utility functions
    print("\n3. Testing utility functions:")
    print(f"   Tenant name for user_editora: {get_tenant_name(user_editora)}")
    print(f"   Tenant URL for user_editora: {get_tenant_url(user_editora)}")
    print(f"   Tenant name for user_company_a: {get_tenant_name(user_company_a)}")
    print(f"   Tenant URL for user_company_a: {get_tenant_url(user_company_a)}")
    
    # Test 4: Test direct tenant lookup
    print("\n4. Testing direct tenant lookup:")
    company_b_tenant = get_tenant_by_id("company_b")
    print(f"   Company B tenant: {company_b_tenant.name} - {company_b_tenant.url}")
    
    # Test 5: Test all tenants
    print("\n5. All available tenants:")
    all_tenants = get_all_tenants()
    for tenant_id, tenant in all_tenants.items():
        print(f"   {tenant_id}: {tenant.name} - {tenant.url}")
    
    # Test 6: Test default tenant fallback
    print("\n6. Testing default tenant fallback:")
    user_no_tenant = UserData(
        id="user-3",
        user_info=UserInfo(email="user3@example.com", first_name="Bob", last_name="Johnson")
        # No tenant_id specified, should use default
    )
    print(f"   User: {user_no_tenant.user_info.first_name} {user_no_tenant.user_info.last_name}")
    print(f"   Tenant ID: {user_no_tenant.tenant_id}")
    print(f"   Tenant Name: {get_tenant_name(user_no_tenant)}")
    print(f"   Tenant URL: {get_tenant_url(user_no_tenant)}")
    
    print("\n✅ All tests completed successfully!")
    print("=" * 50)

if __name__ == "__main__":
    test_tenant_system() 