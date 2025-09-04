#!/usr/bin/env python3

import sys
import os
import requests
import json
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from logger import logger

def test_jenna_cooper_api_with_title():
    """Test Jenna Cooper LA API endpoint with title parameter"""
    
    # Test cases: (title, address)
    test_cases = [
        ("WEST HOLLYWOOD", "337 NORTH CROFT AVENUE"),
        ("BEVERLY HILLS", "1234 BEVERLY DRIVE"),
        ("MALIBU", "5678 PACIFIC COAST HIGHWAY"),
    ]
    
    # API endpoint (adjust as needed)
    base_url = "http://localhost:8080"  # Local development
    # base_url = "https://your-api-endpoint.com"  # Production
    
    for title, address in test_cases:
        logger.info(f"\n{'='*60}")
        logger.info(f"Testing API with title: '{title}'")
        logger.info(f"Address: '{address}'")
        logger.info(f"{'='*60}")
        
        try:
            # Test fetch_property endpoint
            fetch_property_url = f"{base_url}/fetch_property"
            
            payload = {
                "request_id": f"test-{title.lower().replace(' ', '-')}",
                "property_address": address,
                "address_input_type": "AutoComplete",
                "title": title
            }
            
            logger.info(f"Making request to: {fetch_property_url}")
            logger.info(f"Payload: {json.dumps(payload, indent=2)}")
            
            response = requests.post(fetch_property_url, json=payload)
            
            logger.info(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                logger.success(f"SUCCESS: API call successful for title '{title}'")
                logger.info(f"Response: {json.dumps(result, indent=2)}")
            else:
                logger.error(f"FAILED: API call failed for title '{title}'")
                logger.error(f"Response: {response.text}")
                
        except Exception as e:
            logger.exception(f"ERROR: Exception during API test for title '{title}': {str(e)}")
    
    logger.info(f"\n{'='*60}")
    logger.info("API test completed")
    logger.info(f"{'='*60}")

if __name__ == "__main__":
    test_jenna_cooper_api_with_title() 