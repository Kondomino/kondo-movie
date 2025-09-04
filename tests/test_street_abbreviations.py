import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from utils.str_utils import apply_street_abbreviations, generate_url_slugs, STREET_ABBREVIATIONS

def test_apply_street_abbreviations():
    """Test the apply_street_abbreviations function"""
    
    test_cases = [
        ("123 NORTH MAIN STREET", "123 N MAIN ST"),
        ("456 SOUTH OAK AVENUE", "456 S OAK AVE"),
        ("789 EAST PINE BOULEVARD", "789 E PINE BLVD"),
        ("321 WEST ELM DRIVE", "321 W ELM DR"),
        ("654 NORTHEAST MAPLE PLACE", "654 NE MAPLE PL"),
        ("987 NORTHWEST CEDAR COURT", "987 NW CEDAR CT"),
        ("147 SOUTHEAST BIRCH LANE", "147 SE BIRCH LN"),
        ("258 SOUTHWEST WILLOW WAY", "258 SW WILLOW WAY"),
        ("369 NORTH HIGHLAND PARKWAY", "369 N HIGHLAND PKWY"),
        ("741 SOUTH RIVER HIGHWAY", "741 S RIVER HWY"),
    ]
    
    print("Testing apply_street_abbreviations...")
    for input_text, expected in test_cases:
        result = apply_street_abbreviations(input_text)
        if result == expected:
            print(f"✓ PASS: '{input_text}' -> '{result}'")
        else:
            print(f"✗ FAIL: '{input_text}' -> '{result}' (expected: '{expected}')")
            return False
    
    return True

def test_generate_url_slugs():
    """Test the generate_url_slugs function"""
    
    test_cases = [
        ("123 NORTH MAIN STREET", [
            "123-north-main-street",
            "123northmainstreet", 
            "123-n-main-st",
            "123nmainst"
        ]),
        ("456 SOUTH OAK AVENUE", [
            "456-south-oak-avenue",
            "456southoakavenue",
            "456-s-oak-ave", 
            "456soakave"
        ]),
    ]
    
    print("\nTesting generate_url_slugs...")
    for input_title, expected_slugs in test_cases:
        result_slugs = generate_url_slugs(input_title)
        if result_slugs == expected_slugs:
            print(f"✓ PASS: '{input_title}' -> {result_slugs}")
        else:
            print(f"✗ FAIL: '{input_title}' -> {result_slugs} (expected: {expected_slugs})")
            return False
    
    return True

def test_street_abbreviations_dict():
    """Test that the STREET_ABBREVIATIONS dictionary is complete"""
    
    expected_abbreviations = {
        'STREET': 'ST',
        'AVENUE': 'AVE',
        'BOULEVARD': 'BLVD',
        'DRIVE': 'DR',
        'NORTH': 'N',
        'SOUTH': 'S',
        'EAST': 'E',
        'WEST': 'W',
        'NORTHEAST': 'NE',
        'NORTHWEST': 'NW',
        'SOUTHEAST': 'SE',
        'SOUTHWEST': 'SW'
    }
    
    print("\nTesting STREET_ABBREVIATIONS dictionary...")
    for full_word, abbrev in expected_abbreviations.items():
        if full_word in STREET_ABBREVIATIONS and STREET_ABBREVIATIONS[full_word] == abbrev:
            print(f"✓ PASS: '{full_word}' -> '{abbrev}'")
        else:
            print(f"✗ FAIL: '{full_word}' not found or incorrect")
            return False
    
    return True

def main():
    """Run all tests"""
    print("Running street abbreviation utility tests...\n")
    
    tests = [
        test_apply_street_abbreviations,
        test_generate_url_slugs,
        test_street_abbreviations_dict
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        else:
            print(f"\n❌ Test failed: {test.__name__}")
            return False
    
    print(f"\n✅ All {passed}/{total} tests passed!")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 