#!/usr/bin/env python3
"""
Test for download timeout handling and URL validation
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.property_manager import PropertyManager
from property.address import Address

def test_url_validation():
    """Test that URL validation works correctly"""
    print("Testing URL validation...")
    
    # Create PropertyManager instance
    property_mgr = PropertyManager("test address")
    
    # Test cases for URL validation
    test_cases = [
        {
            "name": "Valid image URL",
            "url": "https://jennacooperla.com/cdn/shop/files/image.jpg",
            "expected": True
        },
        {
            "name": "Valid image URL with query params",
            "url": "https://jennacooperla.com/cdn/shop/files/image.jpg?v=123&width=800",
            "expected": True
        },
        {
            "name": "URL with spaces",
            "url": "https://jennacooperla.com/cdn/shop/files/image.jpg ",
            "expected": False
        },
        {
            "name": "URL with newlines",
            "url": "https://jennacooperla.com/cdn/shop/files/image.jpg\n",
            "expected": False
        },
        {
            "name": "Non-HTTP URL",
            "url": "ftp://example.com/image.jpg",
            "expected": False
        },
        {
            "name": "URL without image extension",
            "url": "https://jennacooperla.com/cdn/shop/files/image",
            "expected": False
        },
        {
            "name": "Empty URL",
            "url": "",
            "expected": False
        },
        {
            "name": "None URL",
            "url": None,
            "expected": False
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n=== Test {i}: {test_case['name']} ===")
        
        try:
            # Validate the URL
            result = property_mgr._is_valid_image_url(test_case['url'])
            
            print(f"✓ URL validation completed")
            print(f"  - Input: {repr(test_case['url'])}")
            print(f"  - Expected: {test_case['expected']}")
            print(f"  - Actual: {result}")
            
            # Check if the result matches expected
            if result == test_case['expected']:
                print(f"✓ Test passed!")
            else:
                print(f"✗ Test failed! Expected {test_case['expected']}, got {result}")
                return False
                
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            return False
    
    print("\n✓ All URL validation tests passed!")
    return True

def test_download_timeout_method():
    """Test that the download timeout method exists and has correct signature"""
    print("\nTesting download timeout method...")
    
    try:
        # Create PropertyManager instance
        property_mgr = PropertyManager("test address")
        
        # Check if the method exists
        if hasattr(property_mgr, '_download_image_with_timeout'):
            print("✓ _download_image_with_timeout method exists")
        else:
            print("✗ _download_image_with_timeout method does not exist")
            return False
        
        # Check if the method is callable
        if callable(property_mgr._download_image_with_timeout):
            print("✓ _download_image_with_timeout method is callable")
        else:
            print("✗ _download_image_with_timeout method is not callable")
            return False
        
        # Check if the method has the correct signature
        import inspect
        sig = inspect.signature(property_mgr._download_image_with_timeout)
        params = list(sig.parameters.keys())
        
        expected_params = ['self', 'url', 'local_path']
        if params == expected_params:
            print("✓ _download_image_with_timeout method has correct signature")
        else:
            print(f"✗ _download_image_with_timeout method has incorrect signature. Expected {expected_params}, got {params}")
            return False
        
        print("✓ Download timeout method tests passed!")
        return True
        
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        return False

if __name__ == "__main__":
    success1 = test_url_validation()
    success2 = test_download_timeout_method()
    
    if success1 and success2:
        print("\n🎉 All download timeout tests completed successfully!")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1) 