#!/usr/bin/env python3

import os
import sys
sys.path.append('src')

from gcp.secret import secret_mgr

def test_mandrill_secret():
    """Test MANDRILL_API_KEY secret access"""
    print("=== Test MANDRILL_API_KEY Secret Access ===")
    
    try:
        # Test accessing the MANDRILL_API_KEY secret
        print("Testing MANDRILL_API_KEY access...")
        secret = secret_mgr.secret('MANDRILL_API_KEY')
        if secret:
            print("✓ MANDRILL_API_KEY accessed successfully")
            print(f"  Length: {len(secret)} characters")
            print(f"  Preview: {secret[:20]}...")
        else:
            print("✗ MANDRILL_API_KEY not found")
        
        return True
        
    except Exception as e:
        print(f"✗ MANDRILL_API_KEY test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_mandrill_secret()
    sys.exit(0 if success else 1) 