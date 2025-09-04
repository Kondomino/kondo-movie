#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.jenna_cooper_la import JennaCooperLA
from logger import logger

def test_jenna_cooper_direct_url():
    """Test Jenna Cooper LA direct URL approach for title search"""
    
    # Test cases: (title, expected_url)
    test_cases = [
        ("WEST HOLLYWOOD", "https://jennacooperla.com/pages/west-hollywood"),
        ("BRENTWOOD PRIVATE ESTATE", "https://jennacooperla.com/pages/brentwood-private-estate"),
        ("MALIBU BEACH HOUSE", "https://jennacooperla.com/pages/malibu-beach-house"),
    ]
    
    engine = JennaCooperLA()
    
    for title, expected_url in test_cases:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing direct URL for title: '{title}'")
        logger.info(f"Expected URL: {expected_url}")
        logger.info(f"{'='*60}")
        
        try:
            # Test the direct URL method
            result = engine._try_direct_url_by_title(title)
            
            if result:
                logger.success(f"SUCCESS: Found property via direct URL for title: '{title}'")
                logger.info(f"MLS Info: {result}")
                if result.media_urls:
                    logger.info(f"Found {len(result.media_urls)} images")
                    for i, img in enumerate(result.media_urls[:3]):  # Show first 3 images
                        logger.info(f"Image {i+1}: {img}")
                else:
                    logger.warning("No images found")
            else:
                logger.error(f"FAILED: No property found via direct URL for title: '{title}'")
                
        except Exception as e:
            logger.exception(f"ERROR: Exception during direct URL test for title '{title}': {str(e)}")
    
    logger.info(f"\n{'='*60}")
    logger.info("Direct URL test completed")
    logger.info(f"{'='*60}")

if __name__ == "__main__":
    test_jenna_cooper_direct_url() 