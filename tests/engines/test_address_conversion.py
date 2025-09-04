#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.str_utils import convert_abbreviations_to_full_format

def test_address_conversion():
    """Test the address conversion function"""
    
    test_cases = [
        ("3144 Nichols Canyon Rd", "3144 NICHOLS CANYON ROAD"),
        ("123 Main St", "123 MAIN STREET"),
        ("456 Oak Ave", "456 OAK AVENUE"),
        ("789 Pine Blvd", "789 PINE BOULEVARD"),
        ("321 Elm Dr", "321 ELM DRIVE"),
    ]
    
    print("Testing address conversion:")
    print("-" * 50)
    
    for input_addr, expected in test_cases:
        result = convert_abbreviations_to_full_format(input_addr)
        status = "✓ PASS" if result == expected else "✗ FAIL"
        print(f"{status} | Input: '{input_addr}'")
        print(f"        | Expected: '{expected}'")
        print(f"        | Got:      '{result}'")
        print()

if __name__ == "__main__":
    test_address_conversion() 