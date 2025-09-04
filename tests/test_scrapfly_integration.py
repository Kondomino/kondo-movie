#!/usr/bin/env python3
"""
Test for Scrapfly integration without custom timeouts
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.jenna_cooper_la import JennaCooperLA

def test_scrapfly_integration():
    """Test that Scrapfly integration works correctly"""
    print("Testing Scrapfly integration...")
    
    # Create Jenna Cooper LA scraper instance
    scraper = JennaCooperLA()
    
    # Test cases for error classification
    test_cases = [
        {
            "name": "Timeout error",
            "error": Exception("Request timed out"),
            "expected": "timeout"
        },
        {
            "name": "404 error",
            "error": Exception("404 Not Found"),
            "expected": "not_found"
        },
        {
            "name": "403 error",
            "error": Exception("403 Forbidden"),
            "expected": "forbidden"
        },
        {
            "name": "Rate limit error",
            "error": Exception("429 Rate Limit Exceeded"),
            "expected": "rate_limit"
        },
        {
            "name": "Server error",
            "error": Exception("500 Internal Server Error"),
            "expected": "server_error"
        },
        {
            "name": "Network error",
            "error": Exception("Connection failed"),
            "expected": "network"
        },
        {
            "name": "Unknown error",
            "error": Exception("Some other error"),
            "expected": "unknown"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n=== Test {i}: {test_case['name']} ===")
        
        try:
            # Test error classification
            result = scraper._classify_error(test_case['error'])
            
            print(f"✓ Error classification completed")
            print(f"  - Input error: {str(test_case['error'])}")
            print(f"  - Expected type: {test_case['expected']}")
            print(f"  - Actual type: {result}")
            
            # Check if the result matches expected
            if result == test_case['expected']:
                print(f"✓ Test passed!")
            else:
                print(f"✗ Test failed! Expected {test_case['expected']}, got {result}")
                return False
                
        except Exception as e:
            print(f"✗ Test failed with exception: {e}")
            return False
    
    print("\n✓ All Scrapfly integration tests passed!")
    return True

def test_scrapfly_method_exists():
    """Test that the new Scrapfly method exists and has correct signature"""
    print("\nTesting Scrapfly method...")
    
    try:
        # Create Jenna Cooper LA scraper instance
        scraper = JennaCooperLA()
        
        # Check if the method exists
        if hasattr(scraper, '_scrape_with_scrapfly'):
            print("✓ _scrape_with_scrapfly method exists")
        else:
            print("✗ _scrape_with_scrapfly method does not exist")
            return False
        
        # Check if the method is callable
        if callable(scraper._scrape_with_scrapfly):
            print("✓ _scrape_with_scrapfly method is callable")
        else:
            print("✗ _scrape_with_scrapfly method is not callable")
            return False
        
        # Check if the method has the correct signature
        import inspect
        sig = inspect.signature(scraper._scrape_with_scrapfly)
        params = list(sig.parameters.keys())
        
        expected_params = ['self', 'url']
        if params == expected_params:
            print("✓ _scrape_with_scrapfly method has correct signature")
        else:
            print(f"✗ _scrape_with_scrapfly method has incorrect signature. Expected {expected_params}, got {params}")
            return False
        
        print("✓ Scrapfly method tests passed!")
        return True
        
    except Exception as e:
        print(f"✗ Test failed with exception: {e}")
        return False

if __name__ == "__main__":
    success1 = test_scrapfly_integration()
    success2 = test_scrapfly_method_exists()
    
    if success1 and success2:
        print("\n🎉 All Scrapfly integration tests completed successfully!")
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1) 