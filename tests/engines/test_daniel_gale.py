#!/usr/bin/env python3
"""
Test script for Daniel Gale engine implementation.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.daniel_gale import DanielGale
from property.address import Address
from rich import print

def test_daniel_gale_engine():
    print("🧪 Testing Daniel Gale Engine")
    print("=" * 50)
    
    # Test addresses (you can modify these)
    test_addresses = [
        "123 Main Street, New York, NY",
        "456 Park Avenue, Manhattan, NY",
        "789 Fifth Avenue, New York, NY"
    ]
    
    engine = DanielGale()
    
    for address_str in test_addresses:
        print(f"\n📍 Testing address: {address_str}")
        
        try:
            address = Address(address_str, Address.AddressInputType.AutoComplete)
            
            mls_info = engine.get_property_info(address_obj=address, debug=True)
            
            if mls_info:
                print(f"✅ Success! Found property:")
                print(f"   MLS ID: {mls_info.mls_id}")
                print(f"   Price: {mls_info.list_price}")
                print(f"   Description: {mls_info.description[:100]}..." if mls_info.description else "No description")
                print(f"   Specs: {mls_info.specs}")
                print(f"   Images: {len(mls_info.media_urls) if mls_info.media_urls else 0} found")
            else:
                print(f"❌ No property found for this address")
                
        except Exception as e:
            print(f"❌ Error processing address: {str(e)}")
    
    print("\n" + "=" * 50)
    print("✅ Daniel Gale engine test completed!")

if __name__ == '__main__':
    test_daniel_gale_engine() 