#!/usr/bin/env python3

import os
import sys
sys.path.append('src')

from gcp.secret import secret_mgr

def test_secret_simple():
    """Simple Secret Manager test"""
    print("=== Simple Secret Manager Test ===")
    
    try:
        # Test accessing a secret
        print("Testing secret access...")
        secret = secret_mgr.secret('STYTCH_SECRET')
        if secret:
            print("✓ Secret accessed successfully")
            print(f"  Length: {len(secret)} characters")
        else:
            print("✗ Secret not found")
        
        return True
        
    except Exception as e:
        print(f"✗ Secret test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_secret_simple()
    sys.exit(0 if success else 1) 