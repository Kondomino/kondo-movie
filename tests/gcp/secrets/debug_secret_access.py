#!/usr/bin/env python3

import os
import sys
sys.path.append('src')

from google.cloud import secretmanager
from google.oauth2 import service_account
from config.config import settings, DB_SERVICE_ACCOUNT_KEY_FILE_PATH

def debug_secret_access():
    """Debug secret access issues"""
    print("=== Secret Access Debug ===")
    print(f"Project ID: {settings.GCP.PROJECT_ID}")
    print(f"Service account key: {DB_SERVICE_ACCOUNT_KEY_FILE_PATH}")
    print(f"Key file exists: {os.path.exists(DB_SERVICE_ACCOUNT_KEY_FILE_PATH)}")
    
    try:
        # Initialize credentials
        cred = service_account.Credentials.from_service_account_file(DB_SERVICE_ACCOUNT_KEY_FILE_PATH)
        print("✓ Credentials loaded successfully")
        
        # Connect to Secret Manager
        client = secretmanager.SecretManagerServiceClient(credentials=cred)
        print("✓ Connected to Secret Manager")
        
        # Test 1: List all secrets
        print("\n--- Test 1: List All Secrets ---")
        parent = f"projects/{settings.GCP.PROJECT_ID}"
        try:
            secrets = client.list_secrets(request={"parent": parent})
            available_secrets = []
            for secret in secrets:
                secret_name = secret.name.split('/')[-1]
                available_secrets.append(secret_name)
                print(f"  ✓ {secret_name}")
            
            print(f"\nTotal secrets found: {len(available_secrets)}")
            
        except Exception as e:
            print(f"✗ Cannot list secrets: {e}")
            available_secrets = []
        
        # Test 2: Try to access specific secrets
        test_secrets = ['Mandrill_API_Key', 'STYTCH_SECRET', 'JWT_SECRET']
        
        print("\n--- Test 2: Access Specific Secrets ---")
        for secret_name in test_secrets:
            print(f"\nTesting access to: {secret_name}")
            
            # Check if secret exists in the list
            if secret_name in available_secrets:
                print(f"  ✓ Secret '{secret_name}' found in list")
            else:
                print(f"  ✗ Secret '{secret_name}' NOT found in list")
            
            # Try to access the secret
            try:
                name = f"projects/{settings.GCP.PROJECT_ID}/secrets/{secret_name}/versions/latest"
                response = client.access_secret_version(request={"name": name})
                payload = response.payload.data.decode("UTF-8")
                print(f"  ✓ Successfully accessed '{secret_name}'")
                print(f"    Value length: {len(payload)} characters")
                print(f"    Value preview: {payload[:20]}...")
                
            except Exception as e:
                print(f"  ✗ Failed to access '{secret_name}': {e}")
        
        # Test 3: Check secret versions
        print("\n--- Test 3: Check Secret Versions ---")
        for secret_name in test_secrets:
            try:
                parent = f"projects/{settings.GCP.PROJECT_ID}/secrets/{secret_name}"
                versions = client.list_secret_versions(request={"parent": parent})
                version_list = list(versions)
                print(f"  {secret_name}: {len(version_list)} versions")
                for version in version_list:
                    version_id = version.name.split('/')[-1]
                    state = version.state.name
                    print(f"    - Version {version_id}: {state}")
                    
            except Exception as e:
                print(f"  ✗ Cannot check versions for '{secret_name}': {e}")
        
    except Exception as e:
        print(f"✗ Debug failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = debug_secret_access()
    sys.exit(0 if success else 1) 