#!/usr/bin/env python3
"""
Test script to verify user search functionality
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from account.account_actions import AccountActionsHandler
from logger import logger

def test_user_search():
    """Test the user search functionality"""
    
    print("🧪 Testing User Search Functionality")
    print("=" * 50)
    
    handler = AccountActionsHandler()
    
    # Test 1: Search for the specific user that's not appearing
    print("\n📋 Test 1: Searching for 'kondominobr@gmail.com'")
    try:
        result = handler.search_users("kondominobr")
        print(f"   Search results: {len(result.get('users', []))} users found")
        for user in result.get('users', []):
            print(f"   - {user.get('email')} (ID: {user.get('id')})")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 2: List all users to see total count
    print("\n📋 Test 2: Listing all users")
    try:
        result = handler.list_all_users(limit=200)
        total_users = len(result.get('users', []))
        print(f"   Total users in database: {total_users}")
        
        # Check if kondominobr@gmail.com exists in the full list
        kondominobr_found = False
        for user in result.get('users', []):
            if 'kondominobr' in user.get('email', '').lower():
                kondominobr_found = True
                print(f"   ✅ Found kondominobr@gmail.com in full list: {user.get('email')}")
                break
        
        if not kondominobr_found:
            print("   ❌ kondominobr@gmail.com NOT found in full user list")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Search with different queries
    print("\n📋 Test 3: Testing different search queries")
    test_queries = ["kondominobr", "kondominobr@gmail.com", "kondominobr@gmail", "gmail.com"]
    
    for query in test_queries:
        try:
            result = handler.search_users(query)
            print(f"   Query '{query}': {len(result.get('users', []))} results")
        except Exception as e:
            print(f"   Query '{query}': Error - {e}")
    
    # Test 4: Check for any users with similar patterns
    print("\n📋 Test 4: Looking for users with 'kondominobr' pattern")
    try:
        result = handler.list_all_users(limit=500)
        matching_users = []
        for user in result.get('users', []):
            email = user.get('email', '').lower()
            if 'kondominobr' in email or 'kondominio' in email:
                matching_users.append(user.get('email'))
        
        if matching_users:
            print(f"   Found {len(matching_users)} users with similar pattern:")
            for email in matching_users:
                print(f"   - {email}")
        else:
            print("   No users found with 'kondominobr' pattern")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n" + "=" * 50)
    print("✅ User search test completed!")

if __name__ == "__main__":
    test_user_search()
