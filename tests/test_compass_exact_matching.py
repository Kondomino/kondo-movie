#!/usr/bin/env python3
"""
Test script to verify Compass exact address matching
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.compass import Compass
from property.address import Address
from logger import logger

def test_compass_exact_matching():
    """Test that Compass scraper finds exact address matches"""
    
    print("🧪 Testing Compass Exact Address Matching")
    print("=" * 50)
    
    # Test cases
    test_cases = [
        {
            "input": "24992 Normans Way, Calabasas",
            "expected_exact_match": "24992 Normans Way",
            "description": "Should find exact match for 24992 Normans Way"
        },
        {
            "input": "24929 Normans Way, Calabasas", 
            "expected_exact_match": "24929 Normans Way",
            "description": "Should find exact match for 24929 Normans Way"
        },
        {
            "input": "123 Fake Street, Nowhere",
            "expected_exact_match": None,
            "description": "Should not find any match for fake address"
        }
    ]
    
    compass = Compass()
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n📋 Test {i}: {test_case['description']}")
        print(f"   Input: {test_case['input']}")
        
        try:
            # Create address object
            address_obj = Address(test_case['input'])
            
            # Test the exact matching logic
            if test_case['expected_exact_match']:
                # Test with mock API response
                mock_items = [
                    {"text": "24932 Normans Way", "id": "1819964965042158697", "redirectUrl": "/listing/1819964965042158697/view"},
                    {"text": "24972 Normans Way", "id": "218236080544128801", "redirectUrl": "/listing/218236080544128801/view"},
                    {"text": "24992 Normans Way", "id": "218347343416670385", "redirectUrl": "/listing/218347343416670385/view"},
                    {"text": "24929 Normans Way", "id": "218340169990923249", "redirectUrl": "/listing/218340169990923249/view"}
                ]
                
                # Extract just the street address for matching
                input_street = test_case['input'].split(',')[0].strip()
                exact_match = compass._find_exact_address_match(input_street, mock_items)
                
                if exact_match:
                    print(f"   ✅ Found exact match: {exact_match['text']} (ID: {exact_match['id']})")
                    if exact_match['text'] == test_case['expected_exact_match']:
                        print(f"   ✅ Match is correct!")
                    else:
                        print(f"   ❌ Expected '{test_case['expected_exact_match']}' but got '{exact_match['text']}'")
                else:
                    print(f"   ❌ No exact match found (expected: {test_case['expected_exact_match']})")
            else:
                # Test with empty mock response
                mock_items = []
                input_street = test_case['input'].split(',')[0].strip()
                exact_match = compass._find_exact_address_match(input_street, mock_items)
                
                if exact_match is None:
                    print(f"   ✅ Correctly found no match for fake address")
                else:
                    print(f"   ❌ Unexpectedly found match: {exact_match['text']}")
                    
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n📋 Testing Address Normalization")
    print("-" * 30)
    
    # Test address normalization
    test_addresses = [
        "24992 Normans Way",
        "24992 NORMANS WAY", 
        "24992   Normans   Way",
        "24992-Normans-Way",
        "24992 Normans Way, Calabasas, CA"
    ]
    
    for addr in test_addresses:
        normalized = compass._normalize_address_for_matching(addr)
        print(f"   '{addr}' -> '{normalized}'")
    
    print("\n" + "=" * 50)
    print("✅ Compass exact address matching test completed!")

if __name__ == "__main__":
    test_compass_exact_matching()
