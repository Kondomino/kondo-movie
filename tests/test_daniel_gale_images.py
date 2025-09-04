#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.daniel_gale import DanielGale
from property.address import Address
from logger import logger

def test_daniel_gale_image_extraction():
    """Test Daniel Gale image extraction with a known property"""
    
    # Test with a known Daniel Gale property address
    test_address = "14 Shorecliff Place, Great Neck, New York"
    
    logger.info(f"Testing Daniel Gale image extraction for address: {test_address}")
    
    try:
        # Create address object with Daniel Gale tenant_id
        address = Address(test_address, Address.AddressInputType.AutoComplete, tenant_id="daniel_gale")
        
        # Create Daniel Gale scraper
        scraper = DanielGale()
        
        # Get property info
        mls_info = scraper.get_property_info(address_obj=address)
        
        if mls_info and mls_info.media_urls:
            logger.success(f"SUCCESS: Found {len(mls_info.media_urls)} images")
            logger.info("Image URLs:")
            for i, url in enumerate(mls_info.media_urls, 1):
                logger.info(f"  {i}. {url}")
            
            # Check if we got a good number of images (should be 10 based on the HTML you provided)
            if len(mls_info.media_urls) >= 8:  # Allow some flexibility
                logger.success("✅ Image extraction working correctly - found multiple images")
            else:
                logger.warning(f"⚠️ Only found {len(mls_info.media_urls)} images, expected more")
                
        else:
            logger.error("❌ No images found")
            
    except Exception as e:
        logger.exception(f"Test failed: {str(e)}")

if __name__ == "__main__":
    test_daniel_gale_image_extraction() 