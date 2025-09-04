#!/usr/bin/env python3
"""
Test script to verify Daniel Gale scraper functionality.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from property.scrapers.daniel_gale import DanielGale
from property.address import Address

def test_daniel_gale_scraper():
    print("🧪 Testing Daniel Gale Scraper")
    print("=" * 50)
    
    # Test addresses that should work with Daniel Gale
    test_addresses = [
        "30-79 36th Street, Astoria, New York, 11103",
        "63 Lake Road, Manhasset, NY 11030",  # From the hardcoded example
        "123 Main Street, New York, NY 10001",
        "456 Oak Avenue, Brooklyn, NY 11201"
    ]
    
    engine = DanielGale()
    
    for i, address_str in enumerate(test_addresses, 1):
        print(f"\n{i}. Testing address: '{address_str}'")
        print("-" * 50)
        
        try:
            # Create Address object
            address_obj = Address(address_str, Address.AddressInputType.AutoComplete)
            print(f"   ✅ Address object created")
            print(f"   Formatted address: {address_obj.formatted_address}")
            print(f"   Place ID: {address_obj.place_id}")
            
            # Try to get property info
            print(f"   🔍 Calling Daniel Gale scraper...")
            mls_info = engine.get_property_info(address_obj=address_obj)
            
            if mls_info:
                print(f"   ✅ SUCCESS: Found property data")
                print(f"   MLS ID: {mls_info.mls_id}")
                print(f"   List Price: {mls_info.list_price}")
                print(f"   Description: {mls_info.description[:100] if mls_info.description else 'None'}...")
                print(f"   Images: {len(mls_info.media_urls) if mls_info.media_urls else 0} images")
                print(f"   Specs: {mls_info.specs}")
            else:
                print(f"   ❌ FAILED: No property data found")
                
        except Exception as e:
            print(f"   ❌ ERROR: {str(e)}")
            import traceback
            print(f"   Stack trace: {traceback.format_exc()}")
            continue
    
    print("\n✅ Daniel Gale scraper test completed!")
    print("=" * 50)

if __name__ == "__main__":
    test_daniel_gale_scraper() 