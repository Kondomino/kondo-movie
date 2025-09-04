#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.jenna_cooper_la import JennaCooperLA
from property.address import Address
from logger import logger

def test_jenna_cooper_la_extraction():
    """Test Jenna Cooper LA property extraction with a known property"""
    
    # Test with a known Jenna Cooper LA property address
    test_address = "28830 Hampton Place, Los Angeles, CA"
    
    logger.info(f"Testing Jenna Cooper LA property extraction for address: {test_address}")
    
    try:
        # Create address object with tenant_id
        address = Address(test_address, Address.AddressInputType.AutoComplete, "jenna_cooper_la")
        
        # Create Jenna Cooper LA scraper
        scraper = JennaCooperLA()
        
        # Get property info
        mls_info = scraper.get_property_info(address_obj=address)
        
        if mls_info and mls_info.media_urls:
            logger.success(f"SUCCESS: Found {len(mls_info.media_urls)} images")
            logger.info("Image URLs:")
            for i, url in enumerate(mls_info.media_urls, 1):
                logger.info(f"  {i}. {url}")
            
            # Check if we got a good number of images
            if len(mls_info.media_urls) >= 3:  # Allow some flexibility
                logger.success("✅ Image extraction working correctly - found multiple images")
            else:
                logger.warning(f"⚠️ Only found {len(mls_info.media_urls)} images, expected more")
                
        else:
            logger.error("❌ No images found")
            
    except Exception as e:
        logger.exception(f"Test failed: {str(e)}")

if __name__ == "__main__":
    test_jenna_cooper_la_extraction() 