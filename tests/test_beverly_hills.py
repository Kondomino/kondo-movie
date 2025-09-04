#!/usr/bin/env python3
"""
Test script to debug the Beverly Hills address issue
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from property.address import Address
from property.property_manager import PropertyManager
from property.scrapers.compass import Compass
from property.scrapers.coldwell_banker import ColdwellBanker
from property.scrapers.zillow import Zillow
from property.scrapers.corcoran import Corcoran
from logger import logger

def test_address_parsing():
    """Test address parsing for the Beverly Hills address"""
    print("=== Testing Address Parsing ===")
    
    address_str = "412 N Palm Dr, Beverly Hills, CA 90210, USA"
    
    # Test address parsing
    address = Address(address_str, Address.AddressInputType.AutoComplete, tenant_id="editora")
    
    print(f"Input address: {address.input_address}")
    print(f"Formatted address: {address.formatted_address}")
    print(f"Short formatted address: {address.short_formatted_address}")
    print(f"Place ID: {address.place_id}")
    print(f"Plausible matches: {address.plausible_address_matches()}")
    print()

def test_compass_scraper():
    """Test Compass scraper specifically"""
    print("=== Testing Compass Scraper ===")
    
    address_str = "412 N Palm Dr, Beverly Hills, CA 90210, USA"
    address = Address(address_str, Address.AddressInputType.AutoComplete, tenant_id="editora")
    
    compass = Compass()
    
    print(f"Testing Compass scraper with address: {address.input_address}")
    print(f"Address variations: {address.plausible_address_matches()}")
    
    try:
        mls_info = compass.get_property_info(address)
        if mls_info:
            print(f"✅ Compass SUCCESS!")
            print(f"   MLS ID: {mls_info.mls_id}")
            print(f"   Price: {mls_info.list_price}")
            print(f"   Description: {mls_info.description[:100]}..." if mls_info.description else "No description")
            print(f"   Specs: {mls_info.specs}")
            print(f"   Images: {len(mls_info.media_urls)} found")
        else:
            print("❌ Compass returned no data")
    except Exception as e:
        print(f"❌ Compass failed: {str(e)}")
        import traceback
        traceback.print_exc()
    print()

def test_property_manager():
    """Test the full PropertyManager"""
    print("=== Testing PropertyManager ===")
    
    address_str = "412 N Palm Dr, Beverly Hills, CA 90210, USA"
    
    try:
        property_mgr = PropertyManager(
            address=address_str, 
            tenant_id="editora",
            address_input_type=Address.AddressInputType.AutoComplete
        )
        
        print(f"PropertyManager initialized with engines: {[engine.__class__.__name__ for engine in property_mgr.engines]}")
        
        # Test fetch_property
        property, source = property_mgr.fetch_property()
        
        if property:
            print(f"✅ PropertyManager SUCCESS!")
            print(f"   Property ID: {property.id}")
            print(f"   Address: {property.address}")
            print(f"   Source: {source}")
            print(f"   MLS ID: {property.mls_info.mls_id if property.mls_info else 'None'}")
            print(f"   Price: {property.mls_info.list_price if property.mls_info else 'None'}")
            print(f"   Images: {len(property.mls_info.media_urls) if property.mls_info and property.mls_info.media_urls else 0}")
        else:
            print("❌ PropertyManager returned no property")
            
    except Exception as e:
        print(f"❌ PropertyManager failed: {str(e)}")
        import traceback
        traceback.print_exc()
    print()

def test_all_engines():
    """Test all engines individually"""
    print("=== Testing All Engines ===")
    
    address_str = "412 N Palm Dr, Beverly Hills, CA 90210, USA"
    address = Address(address_str, Address.AddressInputType.AutoComplete, tenant_id="editora")
    
    engines = [
        ("Compass", Compass()),
        ("ColdwellBanker", ColdwellBanker()),
        ("Zillow", Zillow()),
        ("Corcoran", Corcoran()),
    ]
    
    for engine_name, engine in engines:
        print(f"\n--- Testing {engine_name} ---")
        try:
            mls_info = engine.get_property_info(address)
            if mls_info:
                print(f"✅ {engine_name} SUCCESS!")
                print(f"   MLS ID: {mls_info.mls_id}")
                print(f"   Price: {mls_info.list_price}")
                print(f"   Images: {len(mls_info.media_urls)}")
            else:
                print(f"❌ {engine_name} returned no data")
        except Exception as e:
            print(f"❌ {engine_name} failed: {str(e)}")

if __name__ == "__main__":
    print("🔍 Debugging Beverly Hills Address Issue")
    print("=" * 50)
    
    # test_address_parsing()
    # test_compass_scraper()
    # test_all_engines()
    test_property_manager()
    
    print("=" * 50)
    print("🏁 Debug complete!") 