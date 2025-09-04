#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.jenna_cooper_la import JennaCooperLA
from property.address import Address
from logger import logger

def test_jenna_cooper_normalization():
    """Test Jenna Cooper LA scraper with address normalization"""
    
    # Test cases: (input_address, expected_normalized)
    test_cases = [
        ("337 NORTH CROFT AVENUE", "337 N. CROFT AVE."),
        ("1234 SOUTH BEVERLY DRIVE", "1234 S. BEVERLY DR."),
        ("5678 EAST PACIFIC COAST HIGHWAY", "5678 E. PACIFIC COAST HWY."),
        ("9012 WEST SUNSET BOULEVARD", "9012 W. SUNSET BLVD."),
    ]
    
    engine = JennaCooperLA()
    
    for input_address, expected_normalized in test_cases:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing address normalization")
        logger.info(f"Input: '{input_address}'")
        logger.info(f"Expected: '{expected_normalized}'")
        logger.info(f"{'='*60}")
        
        try:
            # Test the normalization function directly
            normalized_terms = engine._normalize_address_for_jenna_cooper(input_address)
            logger.info(f"Normalized terms: {normalized_terms}")
            
            # Test with actual property search
            address_obj = Address(input_address, Address.AddressInputType.AutoComplete, "jenna_cooper_la")
            
            # Test address search
            result = engine.get_property_info(address_obj=address_obj)
            
            if result:
                logger.success(f"SUCCESS: Found property for address '{input_address}'")
                logger.info(f"MLS Info: {result}")
                if result.media_urls:
                    logger.info(f"Found {len(result.media_urls)} images")
                else:
                    logger.warning("No images found")
            else:
                logger.error(f"FAILED: No property found for address '{input_address}'")
                
        except Exception as e:
            logger.exception(f"ERROR: Exception during normalization test for '{input_address}': {str(e)}")
    
    logger.info(f"\n{'='*60}")
    logger.info("Address normalization test completed")
    logger.info(f"{'='*60}")

if __name__ == "__main__":
    test_jenna_cooper_normalization() 