#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.jenna_cooper_la import JennaCooperLA
from property.address import Address
from logger import logger

def test_jenna_cooper_specific():
    """Test Jenna Cooper LA scraper with the specific property we know exists"""
    
    # Test the specific property we know exists
    test_address = "337 NORTH CROFT AVENUE"
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Testing specific property: '{test_address}'")
    logger.info(f"{'='*60}")
    
    try:
        # Create address object
        address_obj = Address(test_address, Address.AddressInputType.AutoComplete, "jenna_cooper_la")
        
        # Test property search
        engine = JennaCooperLA()
        result = engine.get_property_info(address_obj=address_obj)
        
        if result:
            logger.success(f"SUCCESS: Found property for address '{test_address}'")
            logger.info(f"MLS Info: {result}")
            if result.media_urls:
                logger.info(f"Found {len(result.media_urls)} images")
                for i, img in enumerate(result.media_urls[:5]):  # Show first 5 images
                    logger.info(f"Image {i+1}: {img}")
            else:
                logger.warning("No images found")
        else:
            logger.error(f"FAILED: No property found for address '{test_address}'")
            
    except Exception as e:
        logger.exception(f"ERROR: Exception during test for '{test_address}': {str(e)}")
    
    logger.info(f"\n{'='*60}")
    logger.info("Specific property test completed")
    logger.info(f"{'='*60}")

if __name__ == "__main__":
    test_jenna_cooper_specific() 