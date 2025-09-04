#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.address import Address
from property.scrapers.daniel_gale import DanielGale
from logger import logger

def test_daniel_gale_scraper():
    """Test Daniel Gale scraper with various addresses"""
    
    test_addresses = [
        "63 Lake Road, Manhasset, NY 11030",
        "123 Main Street, New York, NY 10001",
        "456 Oak Avenue, Brooklyn, NY 11201"
    ]
    
    scraper = DanielGale()
    
    for address_str in test_addresses:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing address: {address_str}")
        logger.info(f"{'='*60}")
        
        try:
            # Create Address object
            address_obj = Address(address_str, Address.AddressInputType.AutoComplete)
            
            logger.info(f"Address object created successfully:")
            logger.info(f"  - Input address: {address_obj.input_address}")
            logger.info(f"  - Formatted address: {address_obj.formatted_address}")
            logger.info(f"  - Short formatted address: {address_obj.short_formatted_address}")
            logger.info(f"  - Place ID: {address_obj.place_id}")
            
            # Test plausible_address_matches
            plausible_matches = address_obj.plausible_address_matches()
            logger.info(f"Plausible address matches ({len(plausible_matches)}):")
            for i, match in enumerate(plausible_matches, 1):
                logger.info(f"  {i}. {match}")
            
            # Test scraper
            logger.info(f"Testing Daniel Gale scraper...")
            result = scraper.get_property_info(address_obj)
            
            if result:
                logger.success(f"SUCCESS: Found property data!")
                logger.info(f"  - MLS ID: {result.mls_id}")
                logger.info(f"  - List Price: {result.list_price}")
                logger.info(f"  - Description: {result.description[:100] if result.description else 'None'}...")
                logger.info(f"  - Media URLs: {len(result.media_urls)} images")
                logger.info(f"  - Specs: {result.specs}")
            else:
                logger.warning(f"No property data found for address: {address_str}")
                
        except Exception as e:
            logger.error(f"ERROR testing address '{address_str}': {str(e)}")
            import traceback
            logger.error(traceback.format_exc())

if __name__ == "__main__":
    test_daniel_gale_scraper() 