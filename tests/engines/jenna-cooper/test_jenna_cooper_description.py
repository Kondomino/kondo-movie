#!/usr/bin/env python3
"""
Test script to verify Jenna Cooper LA description extraction
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from property.scrapers.jenna_cooper_la import JennaCooperLA
from property.address import Address
from logger import logger

def test_description_extraction():
    """Test the description extraction from Jenna Cooper LA HTML structure"""
    
    # Sample HTML structure based on the provided example
    sample_html = """
    <section class="house_property_details" id="house_property_details-template--19110605816063__house_property_details_TwwhQk">
      <div class="container">
        <div class="details_inner">
          <div class="details_content">
            <div class="content_col">
                <h2>SHERMAN OAKS</h2>
                <h3>JUST LISTED | $5,399,000</h3>
            </div>
            <div class="content_col">
                <h4>6 BEDS | 5.5 BATHS |  POOL | 4,696 SF</h4>
                <span class="old_text">
                    <p>Nestled on a coveted, tree-lined street in the heart of Sherman Oaks, just south of Valley Vista, and set back behind mature hedges and gates, this 6 bedroom, 5.5 bath oasis has been seamlessly re-imagined to blend open-plan living with ample space for both entertaining and privacy. Inside, the light-filled great room features vaulted ceilings and stunning architectural details throughout.</p>
                </span>
            </div>
        </div>
      </div>
    </section>
    """
    
    # Create a mock selector (this is a simplified test)
    from parsel import Selector
    selector = Selector(text=sample_html)
    
    # Test the description extraction
    jenna_cooper = JennaCooperLA()
    
    # Test the enhanced description extraction
    desc_selectors = [
        ".house_property_details .old_text p::text",
        ".house_property_details .old_text::text",
        "[class*='house_property_details'] .old_text p::text",
        "[class*='house_property_details'] .old_text::text",
        ".old_text p::text",
        ".old_text::text",
    ]
    
    print("Testing description extraction...")
    for selector_pattern in desc_selectors:
        desc_elements = selector.css(selector_pattern).getall()
        if desc_elements:
            description_text = ' '.join(desc_elements).strip()
            print(f"✓ Found description using selector: {selector_pattern}")
            print(f"  Description: {description_text[:100]}...")
            break
    else:
        print("✗ No description found with any selector")
    
    # Test property title extraction
    title_selectors = [
        ".house_property_details h2::text",
        "[class*='house_property_details'] h2::text",
        "h2::text"
    ]
    
    print("\nTesting property title extraction...")
    for title_selector in title_selectors:
        title_elements = selector.css(title_selector).getall()
        if title_elements:
            property_title = ' '.join(title_elements).strip()
            print(f"✓ Found property title: {property_title}")
            break
    else:
        print("✗ No property title found")
    
    # Test price/status extraction
    price_selectors = [
        ".house_property_details h3::text",
        "[class*='house_property_details'] h3::text",
        "h3::text"
    ]
    
    print("\nTesting price/status extraction...")
    for price_selector in price_selectors:
        price_elements = selector.css(price_selector).getall()
        if price_elements:
            price_status_text = ' '.join(price_elements).strip()
            print(f"✓ Found price/status: {price_status_text}")
            break
    else:
        print("✗ No price/status found")
    
    # Test specifications extraction
    specs_selectors = [
        ".house_property_details h4::text",
        "[class*='house_property_details'] h4::text",
        "h4::text"
    ]
    
    print("\nTesting specifications extraction...")
    for specs_selector in specs_selectors:
        specs_elements = selector.css(specs_selector).getall()
        if specs_elements:
            specs_text = ' '.join(specs_elements).strip()
            print(f"✓ Found specs: {specs_text}")
            break
    else:
        print("✗ No specifications found")

if __name__ == "__main__":
    test_description_extraction() 