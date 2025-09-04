#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.jenna_cooper_la import JennaCooperLA
from property.address import Address
from logger import logger

def test_jenna_cooper_title_search():
    """Test Jenna Cooper LA scraper with title search"""
    
    # Test cases: (title, expected_address)
    test_cases = [
        ("WEST HOLLYWOOD", "337 NORTH CROFT AVENUE"),
        ("BEVERLY HILLS", "1234 BEVERLY DRIVE"),
        ("MALIBU", "5678 PACIFIC COAST HIGHWAY"),
    ]
    
    engine = JennaCooperLA()
    
    for title, expected_address in test_cases:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing title search: '{title}'")
        logger.info(f"Expected address: '{expected_address}'")
        logger.info(f"{'='*60}")
        
        try:
            # Create address object with the expected address
            address_obj = Address(expected_address, Address.AddressInputType.AutoComplete, "jenna_cooper_la")
            
            # Test title search
            result = engine.get_property_info(address_obj=address_obj, title=title)
            
            if result:
                logger.success(f"SUCCESS: Found property for title '{title}'")
                logger.info(f"MLS Info: {result}")
                if result.media_urls:
                    logger.info(f"Found {len(result.media_urls)} images")
                else:
                    logger.warning("No images found")
            else:
                logger.error(f"FAILED: No property found for title '{title}'")
                
        except Exception as e:
            logger.exception(f"ERROR: Exception during title search for '{title}': {str(e)}")
    
    logger.info(f"\n{'='*60}")
    logger.info("Title search test completed")
    logger.info(f"{'='*60}")

if __name__ == "__main__":
    test_jenna_cooper_title_search() 