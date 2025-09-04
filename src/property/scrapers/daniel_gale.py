import requests
from bs4 import BeautifulSoup
import json
import jmespath
import argparse
import re
import time
from rich import print
from urllib.parse import quote_plus

from scrapfly import ScrapeConfig, ScrapflyClient

from logger import logger
from config.config import settings
from property.scrapers.scraper_base import ScraperBase
from property.property_model import PropertyModel
from property.address import Address
from gcp.secret import secret_mgr
from utils.str_utils import apply_street_abbreviations
from property.scrapers.config.config import ScraperConfig
import time

class DanielGale(ScraperBase):
    def __init__(self):
        self.scrapfly_client = ScrapflyClient(key=secret_mgr.secret(settings.Secret.SCRAPFLY_API_KEY))
        self.tenant_id = "daniel_gale"
    
    def get_property_info(self, address_obj: Address, debug=False) -> PropertyModel.MLSInfo:
        
        logger.info(f"[DANIEL_GALE] Starting property search for address: '{address_obj.input_address}'")
        logger.info(f"[DANIEL_GALE] Formatted address: '{address_obj.formatted_address}'")
        logger.info(f"[DANIEL_GALE] Short formatted address: '{address_obj.short_formatted_address}'")
        logger.info(f"[DANIEL_GALE] Place ID: '{address_obj.place_id}'")

        # For Daniel Gale, we'll use the formatted address directly since it works better with their search
        # The Address class is working fine, we just need to use the right address format for this engine
        address_to_search = address_obj.formatted_address or address_obj.input_address
            
        logger.info(f"[DANIEL_GALE] Using address for search: '{address_to_search}'")
            
        # Strategy 1: Try Daniel Gale direct search URL
        logger.info(f"[DANIEL_GALE] Strategy 1: Trying Daniel Gale direct search URL")
        result = self._try_daniel_gale_direct_search(address_to_search, address_obj)
        if result:
            logger.success(f"[DANIEL_GALE] SUCCESS: Found property via direct search for address: '{address_to_search}'")
            return result
        else:
            logger.warning(f"[DANIEL_GALE] Strategy 1 failed for address: '{address_to_search}'")
        
        # Strategy 2: Direct property URL construction (deactivated - not working properly)
        # logger.info(f"[DANIEL_GALE] Strategy 2: Trying direct property URL construction")
        # result = self._try_direct_property_url(address_to_search)
        # if result:
        #     logger.success(f"[DANIEL_GALE] SUCCESS: Found property via direct URL for address: '{address_to_search}'")
        #     return result
        # else:
        #     logger.warning(f"[DANIEL_GALE] Strategy 2 failed for address: '{address_to_search}'")
                
        logger.error(f"[DANIEL_GALE] FAILED: No property found for any address variation")
        logger.error(f"[DANIEL_GALE] Tried addresses: {list(address_obj.plausible_address_matches())}")
        return None
    
    def _try_direct_property_url(self, address: str) -> PropertyModel.MLSInfo:
        """Try to construct and access direct property URLs based on address patterns"""
        
        logger.info(f"[DANIEL_GALE] _try_direct_property_url called with address: '{address}'")
        
        # Parse address components
        address_parts = address.split(',')
        if len(address_parts) < 2:
            logger.warning(f"[DANIEL_GALE] Address format invalid, need at least 2 parts: '{address}'")
            return None
            
        street_address = address_parts[0].strip()
        city_state = address_parts[1].strip() if len(address_parts) > 1 else ""
        
        logger.info(f"[DANIEL_GALE] Parsed address components:")
        logger.info(f"[DANIEL_GALE]   - Street address: '{street_address}'")
        logger.info(f"[DANIEL_GALE]   - City/State: '{city_state}'")
        
        # Extract street number and name
        street_parts = street_address.split()
        if len(street_parts) < 2:
            logger.warning(f"[DANIEL_GALE] Street address format invalid: '{street_address}'")
            return None
            
        street_number = street_parts[0]
        street_name = ' '.join(street_parts[1:])
        
        logger.info(f"[DANIEL_GALE] Street components:")
        logger.info(f"[DANIEL_GALE]   - Street number: '{street_number}'")
        logger.info(f"[DANIEL_GALE]   - Street name: '{street_name}'")
        
        # Extract city and state
        city_state_parts = city_state.split()
        if len(city_state_parts) < 2:
            logger.warning(f"[DANIEL_GALE] City/State format invalid: '{city_state}'")
            return None
            
        # Find state (usually last part)
        state = city_state_parts[-1]
        city = ' '.join(city_state_parts[:-1])
        
        logger.info(f"[DANIEL_GALE] Location components:")
        logger.info(f"[DANIEL_GALE]   - City: '{city}'")
        logger.info(f"[DANIEL_GALE]   - State: '{state}'")
        
        # Try to construct the direct URL based on the known pattern
        # From the example: /sales/detail/697-l-516-h9scnn/63-lake-road-manhasset-ny-11030
        # We'll try with a generic property ID and the address slug
        address_slug = f"{street_number}-{street_name.lower().replace(' ', '-')}-{city.lower().replace(' ', '-')}-{state.lower()}"
        
        logger.info(f"[DANIEL_GALE] Generated address slug: '{address_slug}'")
        
        # Try with different property ID patterns
        property_id_patterns = [
            "697-l-516-h9scnn",  # From the known example
            "*-*-*-*",  # Generic pattern
        ]
        
        logger.info(f"[DANIEL_GALE] Trying {len(property_id_patterns)} property ID patterns")
        
        for prop_id in property_id_patterns:
            try:
                # Construct the direct URL
                direct_url = f"https://www.sothebysrealty.com/danielgalesir/eng/sales/detail/{prop_id}/{address_slug}"
                
                logger.info(f"[DANIEL_GALE] Trying direct URL: {direct_url}")
                
                result = self._extract_from_property_page(direct_url)
                if result:
                    logger.success(f"[DANIEL_GALE] SUCCESS: Found property via direct URL: {direct_url}")
                    return result
                else:
                    logger.warning(f"[DANIEL_GALE] Direct URL returned no data: {direct_url}")
                    
            except Exception as e:
                logger.error(f"[DANIEL_GALE] Direct URL {direct_url} failed: {str(e)}")
                continue
        
        # If direct URL doesn't work, try search-based approach
        logger.info(f"[DANIEL_GALE] Direct URL approach failed, trying search-based approach")
        try:
            search_url = f"https://www.sothebysrealty.com/danielgalesir/eng/search?q={quote_plus(address)}"
            logger.info(f"[DANIEL_GALE] Search URL: {search_url}")
            
            search_response = self.scrapfly_client.scrape(
                ScrapeConfig(search_url, country="US", asp=True)
            )
            search_response.raise_for_result()
            
            # Look for property links that might match our pattern
            property_links = search_response.selector.css("a[href*='/sales/detail/']::attr(href)").getall()
            logger.info(f"[DANIEL_GALE] Found {len(property_links)} property links in search results")
            
            for i, link in enumerate(property_links[:5]):  # Only check first 5 links
                logger.info(f"[DANIEL_GALE] Checking property link {i+1}: {link}")
                if self._address_matches_pattern(address, link):
                    logger.info(f"[DANIEL_GALE] Address matches pattern for link: {link}")
                    # Found a matching property link, try to extract data
                    full_url = f"https://www.sothebysrealty.com{link}" if link.startswith('/') else link
                    result = self._extract_from_property_page(full_url)
                    if result:
                        logger.success(f"[DANIEL_GALE] SUCCESS: Found property via search link: {full_url}")
                        return result
                    else:
                        logger.warning(f"[DANIEL_GALE] Search link returned no data: {full_url}")
                else:
                    logger.debug(f"[DANIEL_GALE] Address does not match pattern for link: {link}")
                    
        except Exception as e:
            logger.error(f"[DANIEL_GALE] Search-based direct URL approach failed: {str(e)}")
                
        logger.warning(f"[DANIEL_GALE] All direct URL strategies failed for address: '{address}'")
        return None
    
    def _try_daniel_gale_direct_search(self, address: str, address_obj: Address = None) -> PropertyModel.MLSInfo:
        """Use Daniel Gale's direct search URL format to find properties"""
        
        logger.info(f"[DANIEL_GALE] _try_daniel_gale_direct_search called with address: '{address}'")
        
        # Format the address for the search URL
        # Convert "14 Shorecliff Place, Great Neck, New York" to "14+shorecliff+place+great+neck+new+york"
        # Use the original input address format to preserve "Shorecliff" as one word
        if address_obj and hasattr(address_obj, 'input_address'):
            search_address = address_obj.input_address.lower().replace(' ', '+').replace(',', '')
        else:
            search_address = address.lower().replace(' ', '+').replace(',', '')
        
        search_url = f"https://www.sothebysrealty.com/danielgalesir/eng/sales/int/{search_address}-keyword"
        
        logger.info(f"[DANIEL_GALE] Direct search URL: {search_url}")
        
        try:
            response = self.scrapfly_client.scrape(
                ScrapeConfig(search_url, country="US", asp=True)
            )
            response.raise_for_result()
            
            # Look for property links in the search results
            property_links = response.selector.css("a[href*='/sales/detail/']::attr(href)").getall()
            logger.info(f"[DANIEL_GALE] Found {len(property_links)} property links in search results")
            
            if len(property_links) == 0:
                logger.warning(f"[DANIEL_GALE] No property links found in search results")
                return None
            
            # Find the best matching property by comparing addresses
            best_match_url = None
            best_match_score = 0
            
            for i, link in enumerate(property_links):
                # Extract address from the URL slug
                slug = link.split('/')[-1].replace('-', ' ')
                logger.info(f"[DANIEL_GALE] Property {i+1}: {slug}")
                
                # Calculate similarity score
                from difflib import SequenceMatcher
                def normalize(s):
                    return ''.join(e for e in s.lower() if e.isalnum())
                
                norm_search_address = normalize(address)
                norm_slug = normalize(slug)
                similarity = SequenceMatcher(None, norm_search_address, norm_slug).ratio()
                
                logger.info(f"[DANIEL_GALE] Property {i+1} similarity: {similarity:.3f}")
                
                if similarity > best_match_score:
                    best_match_score = similarity
                    best_match_url = link
                    logger.info(f"[DANIEL_GALE] New best match: {slug} (similarity: {similarity:.3f})")
            
            if best_match_url:
                full_url = f"https://www.sothebysrealty.com{best_match_url}" if best_match_url.startswith('/') else best_match_url
                logger.info(f"[DANIEL_GALE] Selected best matching property: {full_url} (similarity: {best_match_score:.3f})")
            else:
                # Fallback to first result if no good match found
                first_property_link = property_links[0]
                full_url = f"https://www.sothebysrealty.com{first_property_link}" if first_property_link.startswith('/') else first_property_link
                logger.info(f"[DANIEL_GALE] Fallback to first property: {full_url}")
            
            # Extract property data from the selected property page
            result = self._extract_from_property_page(full_url)
            if result:
                logger.success(f"[DANIEL_GALE] SUCCESS: Extracted property data from direct search")
                return result
            else:
                logger.warning(f"[DANIEL_GALE] Failed to extract data from selected property page")
                return None
                
        except Exception as e:
            logger.exception(f"[DANIEL_GALE] Direct search failed: {str(e)}")
        return None
    
    def _address_matches_pattern(self, address: str, url: str) -> bool:
        """Check if a URL matches our address pattern"""
        address_lower = address.lower()
        url_lower = url.lower()
        
        # Extract key components from address
        address_parts = address_lower.split(',')
        if len(address_parts) < 2:
            return False
            
        street_address = address_parts[0].strip()
        city_state = address_parts[1].strip()
        
        # Check if street address and city are in the URL
        street_parts = street_address.split()
        if len(street_parts) < 2:
            return False
            
        street_number = street_parts[0]
        street_name = ' '.join(street_parts[1:])
        
        city_state_parts = city_state.split()
        if len(city_state_parts) < 2:
            return False
            
        city = ' '.join(city_state_parts[:-1])
        
        # Check if URL contains our address components
        return (street_number in url_lower and 
                street_name.replace(' ', '-') in url_lower and 
                city.replace(' ', '-') in url_lower)
    
    def _extract_from_property_page(self, property_url: str) -> PropertyModel.MLSInfo:
        """Extract property data from a specific property page"""
        
        try:
            response = self.scrapfly_client.scrape(
                ScrapeConfig(property_url, country="US", asp=True)
            )
            response.raise_for_result()
            
            # Strategy 1: Try to extract from JSON data
            property_data = self._extract_property_data_from_page(response.selector)
            
            if property_data:
                return self._extract_listing_info_json(property_data)
            
            # Strategy 2: Extract from HTML structure (fallback)
            return self._extract_from_html_structure_detailed(response.selector, property_url)
                
        except Exception as e:
            logger.debug(f"Failed to extract from property page {property_url}: {str(e)}")
            
        return None
    
    def _extract_from_html_structure_detailed(self, selector, property_url: str) -> PropertyModel.MLSInfo:
        """Extract property data from HTML structure with detailed parsing"""
        
        try:
            # Extract address from HTML
            address_element = selector.css(".c-ldp-hero-info__address::text").getall()
            if address_element:
                address_text = ''.join(address_element).strip()
            else:
                # Try alternative address selectors
                address_element = selector.css("[class*='address']::text").getall()
                address_text = ''.join(address_element).strip() if address_element else ""
            
            # Extract price
            price_element = selector.css("[class*='price'], [class*='Price']::text").getall()
            price_text = ''.join(price_element).strip() if price_element else ""
            
            # Extract description
            desc_element = selector.css("[class*='description'], [class*='Description']::text").getall()
            description_text = ' '.join(desc_element).strip() if desc_element else ""
            
            # Extract images - Enhanced image extraction for Daniel Gale
            image_urls = self._extract_images_from_daniel_gale_page(selector, property_url)
            
            # Extract specifications
            specs = {}
            
            # Look for beds/bathrooms in various formats
            beds_text = selector.css("[class*='bed'], [class*='Bed']::text").getall()
            if beds_text:
                beds_match = ''.join(beds_text)
                # Extract number from text like "4 Beds" or "4BR"
                import re
                beds_match = re.search(r'(\d+)', beds_match)
                if beds_match:
                    specs['beds'] = int(beds_match.group(1))
            
            baths_text = selector.css("[class*='bath'], [class*='Bath']::text").getall()
            if baths_text:
                baths_match = ''.join(baths_text)
                baths_match = re.search(r'(\d+(?:\.\d+)?)', baths_match)
                if baths_match:
                    specs['bath'] = float(baths_match.group(1))
            
            # Look for square footage
            sqft_text = selector.css("[class*='sqft'], [class*='square']::text").getall()
            if sqft_text:
                sqft_match = ''.join(sqft_text)
                sqft_match = re.search(r'(\d+(?:,\d+)?)', sqft_match)
                if sqft_match:
                    specs['living_size'] = int(sqft_match.group(1).replace(',', ''))
            
            # If we have images or other meaningful data, return it
            if image_urls or address_text or price_text or description_text:
                logger.info(f"Daniel Gale: Found {len(image_urls)} images, address: {address_text[:50]}...")
                return PropertyModel.MLSInfo(
                    mls_id=None,  # We don't have MLS ID from HTML
                    list_price=price_text if price_text else None,
                    description=description_text if description_text else None,
                    specs=specs,
                    media_urls=image_urls,
                )
                
        except Exception as e:
            logger.debug(f"HTML extraction failed: {str(e)}")
            
        return None
    
    def _extract_images_from_daniel_gale_page(self, selector, property_url: str = None) -> list:
        """Extract property images from Daniel Gale property page using multiple strategies"""
        
        image_urls = []
        
        logger.info(f"[DANIEL_GALE] Starting enhanced image extraction with multiple strategies")
        
        # Strategy 1: Playwright-based gallery extraction (NEW PRIMARY STRATEGY)
        if property_url:
            strategy1_images = self._extract_with_playwright_gallery(property_url)
            if strategy1_images and len(strategy1_images) >= ScraperConfig.MIN_IMAGES_FOR_EARLY_RETURN:
                logger.info(f"[DANIEL_GALE] Strategy 1 (Playwright Gallery): Found {len(strategy1_images)} images (returning early)")
                return strategy1_images
            elif strategy1_images:
                image_urls.extend(strategy1_images)
                logger.info(f"[DANIEL_GALE] Strategy 1 (Playwright Gallery): Found {len(strategy1_images)} images (continuing to other strategies)")
        
        # Strategy 2: Extract from preload links in head
        strategy2_images = self._extract_from_preload_links_enhanced(selector)
        if strategy2_images:
            image_urls.extend(strategy2_images)
            logger.info(f"[DANIEL_GALE] Strategy 2 (Preload Links): Found {len(strategy2_images)} images")
        
        # Strategy 3: Extract from standard Swiper carousel
        strategy3_images = self._extract_from_standard_swiper(selector)
        if strategy3_images:
            image_urls.extend(strategy3_images)
            logger.info(f"[DANIEL_GALE] Strategy 3 (Standard Swiper): Found {len(strategy3_images)} images")
        
        # Strategy 4: Extract from fullscreen Swiper carousel
        strategy4_images = self._extract_from_fullscreen_swiper(selector)
        if strategy4_images:
            image_urls.extend(strategy4_images)
            logger.info(f"[DANIEL_GALE] Strategy 4 (Fullscreen Swiper): Found {len(strategy4_images)} images")
        
        # Strategy 5: Extract from src attributes as fallback
        strategy5_images = self._extract_from_src_attributes(selector)
        if strategy5_images:
            image_urls.extend(strategy5_images)
            logger.info(f"[DANIEL_GALE] Strategy 5 (Src Attributes): Found {len(strategy5_images)} images")
        
        # Strategy 6: Extract from legacy preload links
        strategy6_images = self._extract_from_preload_links(selector)
        if strategy6_images:
            image_urls.extend(strategy6_images)
            logger.info(f"[DANIEL_GALE] Strategy 6 (Legacy Preload Links): Found {len(strategy6_images)} images")
        
        # Strategy 7: Extract from data attributes
        strategy7_images = self._extract_from_data_attributes(selector)
        if strategy7_images:
            image_urls.extend(strategy7_images)
            logger.info(f"[DANIEL_GALE] Strategy 7 (Data Attributes): Found {len(strategy7_images)} images")
        
        # Strategy 8: Extract from JSON data
        strategy8_images = self._extract_from_json_data(selector)
        if strategy8_images:
            image_urls.extend(strategy8_images)
            logger.info(f"[DANIEL_GALE] Strategy 8 (JSON Data): Found {len(strategy8_images)} images")
        
        # Get total image count from aria-label attributes
        total_images = self._get_total_image_count_from_aria_labels(selector)
        if total_images > 0:
            logger.info(f"[DANIEL_GALE] Detected {total_images} total images from aria-label attributes")
        
        # Remove duplicates while preserving order
        unique_images = list(dict.fromkeys(image_urls))
        
        # Final filtering to ensure we only get property images
        filtered_images = self._filter_property_images(unique_images)
        
        # Limit based on detected total or reasonable maximum
        max_images = total_images if total_images > 0 else ScraperConfig.MAX_IMAGES_PER_PROPERTY
        final_images = filtered_images[:max_images]
        
        logger.info(f"[DANIEL_GALE] Standard extraction complete: {len(final_images)} property images from {len(image_urls)} total images (max: {max_images})")
        
        return final_images

    def _extract_with_playwright_gallery(self, property_url: str) -> list:
        """Extract images using Playwright by clicking 'View Gallery' button and extracting from swiper"""
        try:
            # Import Playwright here to avoid dependency issues if not installed
            from playwright.sync_api import sync_playwright
            
            logger.info(f"[DANIEL_GALE] Starting Playwright gallery extraction for: {property_url}")
            
            # Check if Playwright is properly installed
            if not self._check_playwright_installation():
                logger.error("[DANIEL_GALE] Playwright not properly installed, skipping gallery extraction")
                return []
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                try:
                    # Navigate to the property page
                    page.goto(property_url, timeout=30000)
                    logger.info("[DANIEL_GALE] Page loaded successfully")
                    
                    # Look for the "View Gallery" button
                    gallery_button_selectors = [
                        "button.c-ldp-hero-info__fullscreen-btn",
                        "button:has-text('View gallery')",
                        "[class*='fullscreen-btn']",
                        "button:has-text('gallery')"
                    ]
                    
                    gallery_button = None
                    for selector in gallery_button_selectors:
                        try:
                            gallery_button = page.wait_for_selector(selector, timeout=5000)
                            if gallery_button:
                                logger.info(f"[DANIEL_GALE] Found gallery button with selector: {selector}")
                                break
                        except:
                            continue
                    
                    if not gallery_button:
                        logger.warning("[DANIEL_GALE] Gallery button not found, trying to extract from existing swiper")
                        # Try to extract from existing swiper if no button found
                        return self._extract_from_existing_swiper(page)
                    
                    # Click the gallery button
                    logger.info("[DANIEL_GALE] Clicking gallery button...")
                    gallery_button.click()
                    
                    # Wait for the gallery to load
                    logger.info("[DANIEL_GALE] Waiting for gallery to load...")
                    time.sleep(2.5)  # Wait 2.5 seconds as requested
                    
                    # Look for the swiper container
                    swiper_selectors = [
                        ".swiper-wrapper",
                        ".swiper .swiper-wrapper",
                        "[class*='swiper-wrapper']"
                    ]
                    
                    swiper_found = False
                    for selector in swiper_selectors:
                        try:
                            page.wait_for_selector(selector, timeout=5000)
                            logger.info(f"[DANIEL_GALE] Found swiper container with selector: {selector}")
                            swiper_found = True
                            break
                        except:
                            continue
                    
                    if not swiper_found:
                        logger.warning("[DANIEL_GALE] Swiper container not found after clicking gallery button")
                        return []
                    
                    # Extract images from swiper slides
                    image_urls = []
                    
                    # Look for all swiper slides
                    slide_selectors = [
                        ".swiper-slide img",
                        ".swiper-wrapper .swiper-slide img",
                        "[class*='swiper-slide'] img"
                    ]
                    
                    for slide_selector in slide_selectors:
                        slides = page.query_selector_all(slide_selector)
                        if slides:
                            logger.info(f"[DANIEL_GALE] Found {len(slides)} slides with selector: {slide_selector}")
                            
                            for i, slide in enumerate(slides):
                                # Get the srcset attribute for highest resolution
                                srcset = slide.get_attribute('srcset')
                                if srcset:
                                    # Parse srcset to get the highest resolution (3840w)
                                    highest_res_url = self._parse_srcset_for_playwright(srcset)
                                    if highest_res_url:
                                        image_urls.append(highest_res_url)
                                        logger.debug(f"[DANIEL_GALE] Added slide {i+1}: {highest_res_url}")
                                
                                # Fallback to src attribute
                                src = slide.get_attribute('src')
                                if src and src.startswith('http') and src not in [url.split(' ')[0] for url in image_urls if ' ' in url]:
                                    image_urls.append(src)
                                    logger.debug(f"[DANIEL_GALE] Added slide {i+1} (src): {src}")
                            
                            if image_urls:
                                break  # Found images, no need to try other selectors
                    
                    # Remove duplicates while preserving order
                    unique_images = list(dict.fromkeys(image_urls))
                    
                    logger.info(f"[DANIEL_GALE] Playwright gallery extraction complete: {len(unique_images)} unique images")
                    return unique_images
                    
                finally:
                    browser.close()
                    
        except Exception as e:
            logger.error(f"[DANIEL_GALE] Playwright gallery extraction failed: {str(e)}")
            return []

    def _extract_from_existing_swiper(self, page) -> list:
        """Extract images from existing swiper without clicking gallery button"""
        try:
            image_urls = []
            
            # Look for existing swiper slides
            slide_selectors = [
                ".swiper-slide img",
                ".swiper-wrapper .swiper-slide img",
                "[class*='swiper-slide'] img"
            ]
            
            for slide_selector in slide_selectors:
                slides = page.query_selector_all(slide_selector)
                if slides:
                    logger.info(f"[DANIEL_GALE] Found {len(slides)} existing slides with selector: {slide_selector}")
                    
                    for i, slide in enumerate(slides):
                        # Get the srcset attribute for highest resolution
                        srcset = slide.get_attribute('srcset')
                        if srcset:
                            # Parse srcset to get the highest resolution (3840w)
                            highest_res_url = self._parse_srcset_for_playwright(srcset)
                            if highest_res_url:
                                image_urls.append(highest_res_url)
                                logger.debug(f"[DANIEL_GALE] Added existing slide {i+1}: {highest_res_url}")
                    
                    if image_urls:
                        break  # Found images, no need to try other selectors
            
            # Remove duplicates while preserving order
            unique_images = list(dict.fromkeys(image_urls))
            
            logger.info(f"[DANIEL_GALE] Existing swiper extraction complete: {len(unique_images)} unique images")
            return unique_images
            
        except Exception as e:
            logger.error(f"[DANIEL_GALE] Existing swiper extraction failed: {str(e)}")
            return []

    def _parse_srcset_for_playwright(self, srcset: str) -> str:
        """Parse srcset and return the highest resolution URL (3840w)"""
        if not srcset:
            return None
        
        try:
            # Split by commas and parse each entry
            entries = [entry.strip() for entry in srcset.split(',')]
            url_width_pairs = []
            
            for entry in entries:
                if entry:
                    # Split by space to separate URL from width descriptor
                    parts = entry.split()
                    if len(parts) >= 2:
                        url = parts[0].strip()
                        width_str = parts[1].strip()
                        
                        # Extract width number
                        import re
                        width_match = re.search(r'(\d+)', width_str)
                        if width_match:
                            width = int(width_match.group(1))
                            url_width_pairs.append((url, width))
            
            # Sort by width (highest first) and return the highest resolution URL
            if url_width_pairs:
                url_width_pairs.sort(key=lambda x: x[1], reverse=True)
                highest_res_url = url_width_pairs[0][0]
                logger.debug(f"[DANIEL_GALE] Selected highest resolution URL: {highest_res_url}")
                return highest_res_url
                
        except Exception as e:
            logger.warning(f"[DANIEL_GALE] Failed to parse srcset: {str(e)}")
            
        return None

    def _check_playwright_installation(self):
        """Check if Playwright browsers are properly installed"""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                # Try to launch a browser to verify installation
                browser = p.chromium.launch(headless=True)
                browser.close()
                logger.info("[DANIEL_GALE] Playwright browsers are properly installed")
                return True
        except Exception as e:
            logger.warning(f"[DANIEL_GALE] Playwright browsers not installed: {str(e)}")
            logger.info("[DANIEL_GALE] Installing Playwright browsers...")
            try:
                import subprocess
                subprocess.run(["playwright", "install", "chromium"], check=True)
                logger.info("[DANIEL_GALE] Playwright browsers installed successfully")
                return True
            except Exception as install_error:
                logger.error(f"[DANIEL_GALE] Failed to install Playwright browsers: {str(install_error)}")
                return False
    
    def _extract_from_standard_swiper(self, selector) -> list:
        """Strategy 1: Extract images from standard Swiper carousel"""
        image_urls = []
        
        # Enhanced selectors for different Swiper implementations
        swiper_selectors = [
            # Standard Swiper selectors
            ".swiper .swiper-slide img::attr(srcset)",
            ".swiper-wrapper .swiper-slide img::attr(srcset)",
            "[class*='swiper'] [class*='slide'] img::attr(srcset)",
            ".swiper-initialized .swiper-slide img::attr(srcset)",
            ".swiper-horizontal .swiper-slide img::attr(srcset)",
            
            # Alternative carousel structures
            ".carousel .carousel-item img::attr(srcset)",
            ".gallery .gallery-item img::attr(srcset)",
            ".slider .slide img::attr(srcset)",
            
            # Generic image containers
            "[class*='image'] [class*='container'] img::attr(srcset)",
            "[class*='photo'] [class*='gallery'] img::attr(srcset)"
        ]
        
        for selector_pattern in swiper_selectors:
            swiper_images = selector.css(selector_pattern).getall()
            if swiper_images:
                logger.info(f"[DANIEL_GALE] Found {len(swiper_images)} standard Swiper images with selector: {selector_pattern}")
                for img_data in swiper_images:
                    if img_data:
                        highest_res_url = self._parse_srcset_urls(img_data)
                        if highest_res_url:
                            image_urls.append(highest_res_url)
                            logger.debug(f"[DANIEL_GALE] Added standard Swiper image: {highest_res_url}")
                        else:
                            logger.warning(f"[DANIEL_GALE] Failed to parse srcset: {img_data[:100]}...")
        
        return image_urls
    
    def _extract_from_fullscreen_swiper(self, selector) -> list:
        """Strategy 2: Extract images from fullscreen Swiper carousel"""
        image_urls = []
        
        # Fullscreen Swiper selectors
        fullscreen_swiper_selectors = [
            ".m-ldp-hero__fullscreen-swiper .swiper-slide img::attr(srcset)",
            ".m-ldp-hero__fullscreen-swiper-wrapper .swiper-slide img::attr(srcset)",
            "#js-container-to-fullscreen .swiper-slide img::attr(srcset)",
            ".m-ldp-hero__fullscreen .swiper .swiper-slide img::attr(srcset)",
            "[id*='fullscreen'] .swiper-slide img::attr(srcset)",
            ".m-ldp-hero__fullscreen-swiper-container--gallery .swiper-slide img::attr(srcset)"
        ]
        
        for selector_pattern in fullscreen_swiper_selectors:
            fullscreen_images = selector.css(selector_pattern).getall()
            if fullscreen_images:
                logger.info(f"[DANIEL_GALE] Found {len(fullscreen_images)} fullscreen Swiper images with selector: {selector_pattern}")
                for img_data in fullscreen_images:
                    if img_data:
                        highest_res_url = self._parse_srcset_urls(img_data)
                        if highest_res_url:
                            image_urls.append(highest_res_url)
                            logger.debug(f"[DANIEL_GALE] Added fullscreen Swiper image: {highest_res_url}")
                        else:
                            logger.warning(f"[DANIEL_GALE] Failed to parse fullscreen srcset: {img_data[:100]}...")
        
        return image_urls
    
    def _extract_from_src_attributes(self, selector) -> list:
        """Strategy 3: Extract images from src attributes as fallback"""
        image_urls = []
        
        swiper_src_selectors = [
            ".swiper .swiper-slide img::attr(src)",
            ".swiper-wrapper .swiper-slide img::attr(src)",
            "[class*='swiper'] [class*='slide'] img::attr(src)",
            ".swiper-initialized .swiper-slide img::attr(src)",
            ".swiper-horizontal .swiper-slide img::attr(src)",
            # Fullscreen src selectors
            ".m-ldp-hero__fullscreen-swiper .swiper-slide img::attr(src)",
            ".m-ldp-hero__fullscreen-swiper-wrapper .swiper-slide img::attr(src)",
            "#js-container-to-fullscreen .swiper-slide img::attr(src)"
        ]
        
        for selector_pattern in swiper_src_selectors:
            swiper_src_images = selector.css(selector_pattern).getall()
            if swiper_src_images:
                logger.info(f"[DANIEL_GALE] Found {len(swiper_src_images)} src images with selector: {selector_pattern}")
                for img_src in swiper_src_images:
                    if img_src and img_src.startswith('http'):
                        image_urls.append(img_src)
                        logger.debug(f"[DANIEL_GALE] Added src image: {img_src}")
        
        return image_urls
    
    def _extract_from_data_attributes(self, selector) -> list:
        """Strategy 5: Extract images from data attributes"""
        image_urls = []
        
        data_image_selectors = [
            "[data-src]::attr(data-src)",
            "[data-image]::attr(data-image)", 
            "[data-lazy]::attr(data-lazy)",
            "[data-original]::attr(data-original)",
            "img[data-src]::attr(data-src)",
            "img[data-image]::attr(data-image)",
            "[data-gallery]::attr(data-gallery)",
            "[data-images]::attr(data-images)"
        ]
        
        for data_selector in data_image_selectors:
            data_images = selector.css(data_selector).getall()
            if data_images:
                logger.info(f"[DANIEL_GALE] Found {len(data_images)} data attribute images with selector: {data_selector}")
                for img in data_images:
                    if img and img.startswith('http'):
                        image_urls.append(img)
        
        return image_urls
    
    def _extract_from_json_data(self, selector) -> list:
        """Strategy 6: Extract images from JSON data"""
        image_urls = []
        
        script_selectors = [
            "script#__NEXT_DATA__::text",
            "script[type='application/json']::text",
            "script[data-hypernova-key]::text"
        ]
        
        for script_selector in script_selectors:
            script_data = selector.css(script_selector).get()
            if script_data:
                try:
                    json_data = json.loads(script_data)
                    # Look for image arrays in the JSON data
                    image_arrays = self._find_image_arrays_in_json(json_data)
                    if image_arrays:
                        logger.info(f"[DANIEL_GALE] Found {len(image_arrays)} image arrays in JSON data")
                        image_urls.extend(image_arrays)
                except json.JSONDecodeError:
                    continue
        
        return image_urls
    
    def _get_total_image_count_from_aria_labels(self, selector) -> int:
        """Extract total image count from aria-label attributes"""
        aria_labels = selector.css(".swiper-slide[aria-label*='/']::attr(aria-label)").getall()
        total_images = 0
        for label in aria_labels:
            if '/' in label:
                try:
                    # Extract the total number from "X / Y" format
                    total_part = label.split('/')[-1].strip()
                    total_images = max(total_images, int(total_part))
                except (ValueError, IndexError):
                    continue
        
        return total_images
    
    def _filter_property_images(self, image_urls: list) -> list:
        """Filter images to only include property photos - Daniel Gale specific"""
        return self._filter_daniel_gale_images(image_urls)
    
    def _extract_from_preload_links(self, selector) -> list:
        """Extract all property images from preload link elements"""
        image_urls = []
        
        try:
            # Look for link elements with rel="preload" and as="image"
            preload_selectors = [
                "link[rel='preload'][as='image']::attr(imagesrcset)",
                "link[rel='preload'][as='image']::attr(href)"
            ]
            
            for preload_selector in preload_selectors:
                preload_data = selector.css(preload_selector).getall()
                if preload_data:
                    logger.info(f"[DANIEL_GALE] Found {len(preload_data)} preload elements with selector: {preload_selector}")
                    
                    for preload_item in preload_data:
                        if preload_item:
                            if 'imagesrcset' in preload_selector:
                                # Extract URLs from imagesrcset attribute
                                # Format: "url1 96w, url2 128w, url3 256w, ..."
                                urls = preload_item.split(',')
                                for url_part in urls:
                                    url_part = url_part.strip()
                                    if url_part:
                                        # Extract the URL (everything before the space and width)
                                        url = url_part.split(' ')[0]
                                        if url.startswith('http'):
                                            # Use Daniel Gale specific validation
                                            if self._is_valid_daniel_gale_image_url(url):
                                                image_urls.append(url)
                            else:
                                # Direct href attribute
                                if preload_item.startswith('http'):
                                    # Use Daniel Gale specific validation
                                    if self._is_valid_daniel_gale_image_url(preload_item):
                                        image_urls.append(preload_item)
            
            # Remove duplicates while preserving order
            unique_images = list(dict.fromkeys(image_urls))
            
            # Take only the highest resolution version of each image
            # Group by base URL (without width parameter) and take the highest resolution
            base_urls = {}
            for img_url in unique_images:
                # Extract base URL without width parameter
                if 'w=' in img_url:
                    base_url = img_url.split('w=')[0]
                    # Extract width value
                    width_match = re.search(r'w=(\d+)', img_url)
                    if width_match:
                        width = int(width_match.group(1))
                        if base_url not in base_urls or width > base_urls[base_url]['width']:
                            base_urls[base_url] = {'url': img_url, 'width': width}
                else:
                    # If no width parameter, keep as is
                    base_urls[img_url] = {'url': img_url, 'width': 0}
            
            # Extract the highest resolution URLs
            final_images = [item['url'] for item in base_urls.values()]
            
            logger.info(f"[DANIEL_GALE] Extracted {len(final_images)} unique high-resolution images from preload links")
            return final_images
            
        except Exception as e:
            logger.error(f"[DANIEL_GALE] Error extracting from preload links: {str(e)}")
            return []
    
    def _get_total_image_count(self, selector) -> int:
        """Extract total number of images from pagination counter"""
        try:
            # Look for pagination counters that show "X of Y" format
            counter_selectors = [
                ".c-ldp-hero-info__counter span::text",
                ".c-ldp-hero-carousel__pagination span::text",
                "[class*='pagination'] span::text",
                "[class*='counter'] span::text"
            ]
            
            for counter_selector in counter_selectors:
                counter_texts = selector.css(counter_selector).getall()
                if counter_texts:
                    # Look for patterns like "9/11" or "9 of 11"
                    for text in counter_texts:
                        if '/' in text or 'of' in text.lower():
                            # Extract the total number
                            import re
                            match = re.search(r'(\d+)\s*(?:of|/)\s*(\d+)', text.lower())
                            if match:
                                total = int(match.group(2))
                                logger.info(f"[DANIEL_GALE] Found pagination counter: {text} -> {total} total images")
                                return total
            
            # Fallback: look for aria-label attributes
            aria_labels = selector.css("[aria-label*='of']::attr(aria-label)").getall()
            for label in aria_labels:
                import re
                match = re.search(r'(\d+)\s*of\s*(\d+)', label.lower())
                if match:
                    total = int(match.group(2))
                    logger.info(f"[DANIEL_GALE] Found aria-label counter: {label} -> {total} total images")
                    return total
                    
        except Exception as e:
            logger.error(f"[DANIEL_GALE] Error extracting total image count: {str(e)}")
        
        # Default fallback
        logger.warning("[DANIEL_GALE] Could not determine total image count, using default")
        return 10
    
    def _extract_from_main_carousel(self, selector, total_images: int) -> list:
        """Extract images from the main carousel by navigating through all slides"""
        image_urls = []
        
        try:
            # Extract all carousel slides that contain images
            carousel_slide_selectors = [
                ".c-ldp-hero-carousel__wrapper .c-ldp-hero-slide img::attr(srcset)",
                ".c-ldp-hero-carousel__wrapper .c-ldp-hero-slide img::attr(src)",
                ".c-ldp-hero-carousel .c-ldp-hero-slide__photos-wrapper img::attr(srcset)",
                ".c-ldp-hero-carousel .c-ldp-hero-slide__photos-wrapper img::attr(src)"
            ]
            
            for slide_selector in carousel_slide_selectors:
                slide_images = selector.css(slide_selector).getall()
                if slide_images:
                    logger.info(f"[DANIEL_GALE] Found {len(slide_images)} images with selector: {slide_selector}")
                    for img_data in slide_images:
                        if img_data:
                            if 'srcset' in slide_selector:
                                # Extract the highest resolution image from srcset
                                urls = img_data.split(',')
                                if urls:
                                    # Take the last URL (highest resolution)
                                    last_url = urls[-1].strip().split(' ')[0]
                                    if last_url.startswith('http'):
                                        image_urls.append(last_url)
                            else:
                                # Direct src attribute
                                if img_data.startswith('http'):
                                    image_urls.append(img_data)
            
            # Remove duplicates and filter out non-property images
            unique_images = []
            for img in image_urls:
                # Use Daniel Gale specific filtering
                if self._is_valid_daniel_gale_image_url(img):
                    unique_images.append(img)
            
            logger.info(f"[DANIEL_GALE] Extracted {len(unique_images)} unique property images from carousel")
            return unique_images[:total_images]  # Limit to the detected total
            
        except Exception as e:
            logger.error(f"[DANIEL_GALE] Error extracting from main carousel: {str(e)}")
            return []
    
    def _find_image_arrays_in_json(self, json_data: dict) -> list:
        """Recursively search JSON for image arrays"""
        image_arrays = []
        
        def search_for_images(obj, path=""):
            if isinstance(obj, dict):
                # Look for common image-related keys
                image_keys = ['images', 'photos', 'gallery', 'media', 'slides', 'carousel']
                for key in image_keys:
                    if key in obj and isinstance(obj[key], list):
                        logger.info(f"[DANIEL_GALE] Found image array at path: {path}.{key}")
                        for item in obj[key]:
                            if isinstance(item, str) and item.startswith('http'):
                                image_arrays.append(item)
                            elif isinstance(item, dict) and 'url' in item:
                                image_arrays.append(item['url'])
                            elif isinstance(item, dict) and 'src' in item:
                                image_arrays.append(item['src'])
                
                # Recursively search nested objects
                for key, value in obj.items():
                    search_for_images(value, f"{path}.{key}")
            elif isinstance(obj, list):
                # Check if this list contains image URLs
                for i, item in enumerate(obj[:3]):  # Only check first 3 items
                    if isinstance(item, str) and item.startswith('http') and any(img_ext in item.lower() for img_ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        image_arrays.append(item)
                    else:
                        search_for_images(item, f"{path}[{i}]")
        
        search_for_images(json_data)
        return image_arrays
    
    def _try_daniel_gale_search(self, address: str) -> PropertyModel.MLSInfo:
        """Scrape all Daniel Gale sales listings and match the address locally (supports partial/fuzzy match)."""
        from difflib import SequenceMatcher
        
        logger.info(f"[DANIEL_GALE] _try_daniel_gale_search called with address: '{address}'")
        
        sales_url = "https://www.sothebysrealty.com/danielgalesir/eng/sales/int"
        logger.info(f"[DANIEL_GALE] Scraping sales page: {sales_url}")
        
        try:
            response = self.scrapfly_client.scrape(
                ScrapeConfig(sales_url, country="US", asp=True)
            )
            response.raise_for_result()
            property_links = response.selector.css("a[href*='/sales/detail/']::attr(href)").getall()
            logger.info(f"[DANIEL_GALE] Found {len(property_links)} property links on sales page.")
            
            if len(property_links) == 0:
                logger.warning(f"[DANIEL_GALE] No property links found on sales page")
                return None
            
            # Normalize input address for matching
            def normalize(s):
                # Apply street abbreviations first
                s = apply_street_abbreviations(s)
                # Remove common words and normalize
                s = s.lower()
                # Remove common words that don't help with matching
                common_words = ['road', 'street', 'avenue', 'drive', 'lane', 'place', 'court', 'way', 'new york', 'ny']
                for word in common_words:
                    s = s.replace(word, '')
                return ''.join(e for e in s if e.isalnum())
            norm_address = normalize(address)
            logger.info(f"[DANIEL_GALE] Normalized address for matching: '{norm_address}'")
            
            best_match = None
            best_ratio = 0.0
            best_url = None
            
            logger.info(f"[DANIEL_GALE] Checking {len(property_links)} property links for matches...")
            
            for i, link in enumerate(property_links):  # Check all properties
                full_url = f"https://www.sothebysrealty.com{link}" if link.startswith('/') else link
                # Try to extract address from the URL slug
                slug = link.split('/')[-1].replace('-', ' ')
                norm_slug = normalize(slug)
                ratio = SequenceMatcher(None, norm_address, norm_slug).ratio()
                
                logger.info(f"[DANIEL_GALE] Link {i+1}: {slug} (ratio: {ratio:.3f})")
                
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_url = full_url
                    logger.info(f"[DANIEL_GALE] New best match: {slug} (ratio: {ratio:.3f})")
                
                # If perfect match, break early
                if ratio > 0.95:
                    best_match = full_url
                    logger.success(f"[DANIEL_GALE] Perfect match found: {slug} (ratio: {ratio:.3f})")
                    break
            
            # If a good match is found, extract property info
            # Lower threshold from 0.6 to 0.4 to catch more potential matches
            if best_match or (best_ratio > 0.4 and best_url):
                target_url = best_match or best_url
                logger.info(f"[DANIEL_GALE] Best match URL: {target_url} (ratio={best_ratio:.2f})")
                result = self._extract_from_property_page(target_url)
                if result:
                    logger.success(f"[DANIEL_GALE] SUCCESS: Extracted property data from search match")
                    return result
                else:
                    logger.warning(f"[DANIEL_GALE] Failed to extract data from best match URL")
            else:
                logger.warning(f"[DANIEL_GALE] No sufficiently close match found for address: '{address}' (best ratio: {best_ratio:.3f})")
                return None
        except Exception as e:
            logger.exception(f"[DANIEL_GALE] Sales page scrape failed: {str(e)}")
            return None
    
    def _extract_property_data_from_page(self, selector) -> dict:
        """Extract property data from Daniel Gale search page"""
        
        # Try to find property data in various script tags
        script_selectors = [
            "script#__NEXT_DATA__::text",
            "script[type='application/json']::text",
            "script[data-hypernova-key]::text"
        ]
        
        for script_selector in script_selectors:
            data = selector.css(script_selector).get()
            if data:
                try:
                    json_data = json.loads(data)
                    property_data = self._find_property_in_json(json_data)
                    if property_data:
                        return property_data
                except json.JSONDecodeError:
                    continue
        
        # Try to extract from HTML structure if JSON not found
        return self._extract_from_html_structure(selector)
    
    def _find_property_in_json(self, json_data: dict) -> dict:
        """Recursively search JSON for property data"""
        
        # Common paths where property data might be stored
        possible_paths = [
            "props.pageProps.property",
            "props.pageProps.listing",
            "props.pageProps.searchResults[0]",
            "props.pageProps.initialState.property",
            "props.pageProps.initialState.listing",
            "data.property",
            "data.listing",
            "searchResults[0]",
            "listings[0]",
            "initialState.property",
            "initialState.listing"
        ]
        
        for path in possible_paths:
            try:
                result = jmespath.search(path, json_data)
                if result and isinstance(result, dict):
                    logger.debug(f"Found property data at path: {path}")
                    return result
            except Exception:
                continue
        
        # If no specific path found, try to find any object that looks like property data
        def find_property_like_data(obj, path=""):
            if isinstance(obj, dict):
                # Check if this looks like property data
                property_keys = ['price', 'address', 'bedrooms', 'bathrooms', 'squareFootage', 'images', 'photos']
                if any(key in obj for key in property_keys):
                    logger.debug(f"Found property-like data at path: {path}")
                    return obj
                
                # Recursively search nested objects
                for key, value in obj.items():
                    result = find_property_like_data(value, f"{path}.{key}")
                    if result:
                        return result
            elif isinstance(obj, list):
                # Check first item in lists
                for i, item in enumerate(obj[:3]):  # Only check first 3 items
                    result = find_property_like_data(item, f"{path}[{i}]")
                    if result:
                        return result
            return None
        
        return find_property_like_data(json_data)
    
    def _extract_from_html_structure(self, selector) -> dict:
        """Extract property data from HTML structure"""
        
        # Look for property cards or listing elements
        property_elements = selector.css(".property-card, .listing-card, [data-property-id]")
        
        if property_elements:
            # Take the first property found
            element = property_elements[0]
            
            property_data = {}
            
            # Extract basic information from HTML attributes or text
            property_data['mls_id'] = element.attrib.get('data-property-id') or element.attrib.get('data-mls-id')
            property_data['price'] = self._extract_price_from_element(element)
            property_data['description'] = self._extract_description_from_element(element)
            property_data['media_urls'] = self._extract_images_from_element(element)
            property_data['specs'] = self._extract_specs_from_element(element)
            
            return property_data
            
        return None
    
    def _extract_price_from_element(self, element) -> str:
        """Extract price from HTML element"""
        price_selectors = [
            ".price::text",
            ".listing-price::text", 
            "[data-price]::attr(data-price)",
            ".property-price::text"
        ]
        
        for selector in price_selectors:
            price = element.css(selector).get()
            if price:
                return price.strip()
        return None
    
    def _extract_description_from_element(self, element) -> str:
        """Extract description from HTML element"""
        desc_selectors = [
            ".description::text",
            ".property-description::text",
            ".listing-description::text",
            "[data-description]::attr(data-description)"
        ]
        
        for selector in desc_selectors:
            desc = element.css(selector).get()
            if desc:
                return desc.strip()
        return None
    
    def _extract_images_from_element(self, element) -> list:
        """Extract image URLs from HTML element"""
        image_selectors = [
            "img::attr(src)",
            "img::attr(data-src)",
            ".property-image img::attr(src)",
            ".listing-image img::attr(src)"
        ]
        
        images = []
        for selector in image_selectors:
            urls = element.css(selector).getall()
            if urls:
                images.extend([url for url in urls if url and url.startswith('http')])
                
        return images[:10]  # Limit to first 10 images
    
    def _extract_specs_from_element(self, element) -> dict:
        """Extract property specifications from HTML element"""
        specs = {}
        
        # Extract beds
        beds = element.css(".beds::text, .bedrooms::text, [data-beds]::attr(data-beds)").get()
        if beds:
            specs['beds'] = int(beds.strip()) if beds.strip().isdigit() else None
            
        # Extract baths
        baths = element.css(".baths::text, .bathrooms::text, [data-baths]::attr(data-baths)").get()
        if baths:
            specs['bath'] = float(baths.strip()) if baths.strip().replace('.', '').isdigit() else None
            
        # Extract square footage
        sqft = element.css(".sqft::text, .square-feet::text, [data-sqft]::attr(data-sqft)").get()
        if sqft:
            specs['living_size'] = int(sqft.strip().replace(',', '')) if sqft.strip().replace(',', '').isdigit() else None
            
        # Extract property type
        prop_type = element.css(".property-type::text, [data-property-type]::attr(data-property-type)").get()
        if prop_type:
            specs['property_type'] = prop_type.strip()
            
        return specs
    
    def _extract_listing_info_json(self, property_data: dict) -> PropertyModel.MLSInfo:
        """Extract listing information from property data"""
        
        mls_id = property_data.get('mls_id') or property_data.get('id')
        list_price = property_data.get('price') or property_data.get('listPrice')
        description = property_data.get('description')
        media_urls = property_data.get('media_urls') or property_data.get('images') or []
        
        # Extract status from various possible locations
        status = (property_data.get('status') or 
                 property_data.get('listingStatus') or
                 property_data.get('mlsStatus') or
                 property_data.get('marketingStatus'))
        
        # Default to "Active" if no status found and property has price
        if not status and list_price:
            status = "Active"
        
        specs = property_data.get('specs', {})
        if not specs:
            # Try to extract specs from property_data directly
            specs = {
                'property_type': property_data.get('propertyType') or property_data.get('homeType'),
                'beds': property_data.get('bedrooms') or property_data.get('beds'),
                'bath': property_data.get('bathrooms') or property_data.get('baths'),
                'living_size': property_data.get('livingArea') or property_data.get('squareFootage'),
                'lot_size': property_data.get('lotSize')
            }
        
        return PropertyModel.MLSInfo(
            mls_id=mls_id,
            list_price=str(list_price) if list_price else None,
            description=description,
            specs=specs,
            media_urls=media_urls,
            status=status
        )


    
    def _parse_srcset_urls(self, srcset: str) -> str:
        """Parse complex srcset strings from Daniel Gale and extract highest resolution URL"""
        if not srcset or ',' not in srcset:
            return None
            
        try:
            # Parse srcset format: "url1 640w, url2 750w, url3 828w, url4 1080w, url5 1200w, url6 1920w, url7 2048w, url8 3840w"
            srcset_parts = srcset.split(',')
            url_width_pairs = []
            
            for part in srcset_parts:
                part = part.strip()
                if part:
                    # Split by space to separate URL from width descriptor
                    url_parts = part.split()
                    if len(url_parts) >= 2:
                        url = url_parts[0].strip()
                        width_str = url_parts[1].strip()
                        
                        # Convert protocol-relative URLs to https
                        if url.startswith('//'):
                            url = f"https:{url}"
                        
                        if url.startswith('http'):
                            # Extract width number
                            import re
                            width_match = re.search(r'(\d+)', width_str)
                            if width_match:
                                width = int(width_match.group(1))
                                url_width_pairs.append((url, width))
            
            # Sort by width (highest first) and return the highest resolution URL
            if url_width_pairs:
                url_width_pairs.sort(key=lambda x: x[1], reverse=True)
                highest_res_url = url_width_pairs[0][0]
                logger.debug(f"[DANIEL_GALE] Extracted highest resolution URL from srcset: {highest_res_url}")
                return highest_res_url
                
        except Exception as e:
            logger.warning(f"[DANIEL_GALE] Failed to parse srcset: {str(e)}")
            
        return None

    def _is_valid_daniel_gale_image_url(self, url: str) -> bool:
        """Validate image URLs specifically for Daniel Gale engine"""
        if not url or not url.startswith('http'):
            return False
        
        # Accept URLs with image extensions
        if any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            return True
        
        # Accept GTS Static URLs (Daniel Gale's image service)
        if 'gtsstatic.net' in url and 'imagereader.aspx' in url:
            return True
        
        # Accept other common image service patterns used by Daniel Gale
        daniel_gale_image_patterns = [
            'api-trestle.corelogic.com',
            'api.bridgedataoutput.com',
            'images.realtor.com',
            'photos.zillowstatic.com',
            'images.compass.com',
            'sothebysrealty.com'
        ]
        
        return any(pattern in url for pattern in daniel_gale_image_patterns)
    
    def _filter_daniel_gale_images(self, image_urls: list) -> list:
        """Filter images to only include valid Daniel Gale property photos"""
        filtered_images = []
        
        for img in image_urls:
            # Skip if it's clearly not a property image
            if any(skip_keyword in img.lower() for skip_keyword in ['logo', 'icon', 'avatar', 'profile', 'button', 'banner', 'advertisement', 'agent', 'team', 'staff', 'broker']):
                continue
            # Include if it looks like a property image or is a valid Daniel Gale URL
            if (any(include_keyword in img.lower() for include_keyword in ['property', 'listing', 'photo', 'image', 'reno', 'gtsstatic', 'sothebys', 'detail', 'hero']) or
                self._is_valid_daniel_gale_image_url(img)):
                filtered_images.append(img)
        
        return filtered_images

    def _extract_from_preload_links_enhanced(self, selector) -> list:
        """Strategy 1: Extract images from enhanced preload links in head section"""
        image_urls = []
        
        try:
            logger.info(f"[DANIEL_GALE] Starting enhanced preload links extraction...")
            
            # Look for link elements with rel="preload" and as="image" in the head
            preload_selectors = [
                "link[rel='preload'][as='image']::attr(imagesrcset)",
                "head link[rel='preload'][as='image']::attr(imagesrcset)"
            ]
            
            for preload_selector in preload_selectors:
                preload_data = selector.css(preload_selector).getall()
                if preload_data:
                    logger.info(f"[DANIEL_GALE] Found {len(preload_data)} enhanced preload elements with selector: {preload_selector}")
                    
                    for i, preload_item in enumerate(preload_data):
                        if preload_item:
                            logger.debug(f"[DANIEL_GALE] Processing preload item {i+1}: {preload_item[:200]}...")
                            
                            # Parse the imagesrcset attribute
                            # Format: "url1 96w, url2 128w, url3 256w, ..."
                            urls = preload_item.split(',')
                            for url_part in urls:
                                url_part = url_part.strip()
                                if url_part:
                                    # Extract the URL (everything before the space and width)
                                    url = url_part.split(' ')[0]
                                    if url.startswith('http'):
                                        # Use Daniel Gale specific validation
                                        if self._is_valid_daniel_gale_image_url(url):
                                            image_urls.append(url)
                                            logger.debug(f"[DANIEL_GALE] Added enhanced preload image: {url}")
            
            # Remove duplicates while preserving order
            unique_images = list(dict.fromkeys(image_urls))
            
            # Take only the highest resolution version of each image
            # Group by base URL (without width parameter) and take the highest resolution
            base_urls = {}
            for img_url in unique_images:
                # Extract base URL without width parameter
                if 'w=' in img_url:
                    base_url = img_url.split('w=')[0]
                    # Extract width value
                    width_match = re.search(r'w=(\d+)', img_url)
                    if width_match:
                        width = int(width_match.group(1))
                        if base_url not in base_urls or width > base_urls[base_url]['width']:
                            base_urls[base_url] = {'url': img_url, 'width': width}
                else:
                    # If no width parameter, keep as is
                    base_urls[img_url] = {'url': img_url, 'width': 0}
            
            # Extract the highest resolution URLs
            final_images = [item['url'] for item in base_urls.values()]
            
            # Sort by width (highest first) to prioritize highest resolution
            final_images.sort(key=lambda x: int(re.search(r'w=(\d+)', x).group(1)) if 'w=' in x and re.search(r'w=(\d+)', x) else 0, reverse=True)
            
            logger.info(f"[DANIEL_GALE] Enhanced preload extraction complete: {len(final_images)} unique high-resolution images")
            logger.debug(f"[DANIEL_GALE] Sample enhanced preload images: {final_images[:3]}")
            
            return final_images
            
        except Exception as e:
            logger.error(f"[DANIEL_GALE] Error extracting from enhanced preload links: {str(e)}")
            return []

# For testing purposes only
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Daniel Gale Scraper')

    parser.add_argument('-a', '--address', required=True, type=str, help='Property address to search for')
    parser.add_argument('-d', '--debug', action='store_true', help='Debug mode')
    parser.add_argument('-t', '--type', choices=['autocomplete', 'freeform'], default='autocomplete', 
                        help='Address input type: autocomplete (uses Google Places API) or freeform (uses usaddress)')
    
    args = parser.parse_args()
    
    # Convert string input type to enum
    input_type = (Address.AddressInputType.AutoComplete 
                 if args.type == 'autocomplete' 
                 else Address.AddressInputType.FreeForm)
    
    address = Address(args.address, input_type)
    
    try:
        engine = DanielGale()
        
        mls_info = engine.get_property_info(
            address_obj=address, 
            debug=True if args.debug else False)
        print(mls_info)
                
    except Exception as e:
        logger.exception(e)
        
        
if __name__ == '__main__':
    main() 
    main() 