#!/usr/bin/env python3
"""
Test script to verify Corcoran CDN URL validation
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.property_manager import PropertyManager
from logger import logger

def test_corcoran_url_validation():
    """Test that Corcoran CDN URLs are properly validated"""
    
    print("🧪 Testing Corcoran CDN URL Validation")
    print("=" * 50)
    
    # Create a PropertyManager instance (we don't need a real address for this test)
    property_mgr = PropertyManager(
        address="123 Test St, New York, NY 10001",
        tenant_id="corcoran_group"
    )
    
    # Test URLs from the logs
    test_urls = [
        # Corcoran CDN URLs (should be valid)
        "https://media-cloud.corcoranlabs.com/ListingFullAPI/RealogyMLS/SC_HHMLS:451687/df483d2500caef8b9dc30120327a5084",
        "https://media-cloud.corcoranlabs.com/ListingFullAPI/RealogyMLS/SC_HHMLS:451687/a0d923632c9fcd81c6ed5621dce9e715",
        "https://corcoranlabs.com/ListingFullAPI/RealogyMLS/SC_HHMLS:451687/test123",
        
        # Other CDN URLs for comparison
        "https://cdn.shopify.com/s/files/1/1234/5678/products/image.jpg",
        "https://jennacooperla.com/cdn/shop/files/image.jpg",
        
        # Regular URLs with extensions
        "https://example.com/image.jpg",
        "https://example.com/image.png",
        
        # Invalid URLs
        "https://example.com/document.pdf",
        "https://example.com/no-extension",
        "",
        "not-a-url"
    ]
    
    print("\n📋 Testing URL Validation")
    print("-" * 30)
    
    for url in test_urls:
        try:
            is_valid = property_mgr._is_valid_image_url(url)
            status = "✅ VALID" if is_valid else "❌ INVALID"
            print(f"{status}: {url}")
            
            if is_valid:
                try:
                    extension = property_mgr._get_file_extension(url)
                    print(f"   📁 Extension: {extension}")
                except Exception as e:
                    print(f"   ❌ Extension error: {e}")
                    
        except Exception as e:
            print(f"❌ ERROR: {url} - {e}")
    
    print("\n📋 Summary")
    print("-" * 30)
    
    # Count results
    corcoran_urls = [url for url in test_urls if 'corcoranlabs.com' in url]
    valid_corcoran = sum(1 for url in corcoran_urls if property_mgr._is_valid_image_url(url))
    
    print(f"Corcoran URLs tested: {len(corcoran_urls)}")
    print(f"Corcoran URLs valid: {valid_corcoran}")
    print(f"Corcoran URLs invalid: {len(corcoran_urls) - valid_corcoran}")
    
    if valid_corcoran == len(corcoran_urls):
        print("✅ All Corcoran URLs are now being accepted!")
    else:
        print("❌ Some Corcoran URLs are still being rejected")
    
    print("\n" + "=" * 50)
    print("✅ Corcoran URL validation test completed!")

if __name__ == "__main__":
    test_corcoran_url_validation()
