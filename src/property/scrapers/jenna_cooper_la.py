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
from utils.str_utils import generate_url_slugs, apply_street_abbreviations, generate_all_abbreviation_variants

PLACEHOLDER_IMAGE_PATH = "/cdn/shop/files/IMAGE_1_-_CORRECT_SHOPIFY_SIZE_9bf6c5ec-cdd0-464f-ad3a-12723735ff3d.jpg"

def _is_placeholder_image(url: str) -> bool:
    url = url.split("?")[0]
    if url.startswith("https:") or url.startswith("http:"):
        url = url.split("://", 1)[-1]
        url = "/" + url.split("/", 1)[-1]
    elif url.startswith("//"):
        url = "/" + url.lstrip("/").split("/", 1)[-1]
    return url.endswith(PLACEHOLDER_IMAGE_PATH)

class JennaCooperLA(ScraperBase):
    def __init__(self):
        self.scrapfly_client = ScrapflyClient(key=secret_mgr.secret(settings.Secret.SCRAPFLY_API_KEY))
        self.tenant_id = "jenna_cooper_la"
    
    def _classify_error(self, error: Exception) -> str:
        """Classify the type of error for better handling"""
        error_str = str(error).lower()
        
        if 'timeout' in error_str or 'timed out' in error_str:
            return 'timeout'
        elif '404' in error_str or 'not found' in error_str:
            return 'not_found'
        elif '403' in error_str or 'forbidden' in error_str:
            return 'forbidden'
        elif '429' in error_str or 'rate limit' in error_str:
            return 'rate_limit'
        elif '500' in error_str or 'server error' in error_str:
            return 'server_error'
        elif 'connection' in error_str or 'network' in error_str:
            return 'network'
        else:
            return 'unknown'
    
    def _scrape_with_scrapfly(self, url: str) -> any:
        """Scrape URL using Scrapfly's built-in retry mechanism"""
        
        try:
            logger.debug(f"[JENNA_COOPER_LA] Scraping URL: {url}")
            
            response = self.scrapfly_client.scrape(
                ScrapeConfig(
                    url, 
                    country="US", 
                    asp=True
                    # Let Scrapfly use its default timeout and retry settings
                )
            )
            response.raise_for_result()
            logger.debug(f"[JENNA_COOPER_LA] Successfully scraped URL: {url}")
            return response
            
        except Exception as e:
            error_type = self._classify_error(e)
            logger.error(f"[JENNA_COOPER_LA] Failed to scrape URL {url} (error type: {error_type}): {str(e)}")
            
            # Log specific error type for debugging
            if error_type == 'timeout':
                logger.warning(f"[JENNA_COOPER_LA] Timeout error - Scrapfly will handle retries")
            elif error_type == 'not_found':
                logger.warning(f"[JENNA_COOPER_LA] Page not found - no point retrying")
            elif error_type == 'forbidden':
                logger.warning(f"[JENNA_COOPER_LA] Access forbidden - no point retrying")
            
            raise
    
    def get_property_info(self, address_obj: Address, debug=False, title: str = None) -> PropertyModel.MLSInfo:
        
        logger.info(f"[JENNA_COOPER_LA] Starting property search for address: '{address_obj.input_address}'")
        logger.info(f"[JENNA_COOPER_LA] Formatted address: '{address_obj.formatted_address}'")
        logger.info(f"[JENNA_COOPER_LA] Short formatted address: '{address_obj.short_formatted_address}'")
        logger.info(f"[JENNA_COOPER_LA] Place ID: '{address_obj.place_id}'")
        if title:
            logger.info(f"[JENNA_COOPER_LA] Title search provided: '{title}'")

        # For Jenna Cooper LA, we'll use the formatted address directly
        address_to_search = address_obj.formatted_address or address_obj.input_address
        
        # For Jenna Cooper LA, we need to use the original input address for normalization
        # because Google Places API changes "NORTH" to "N" which breaks our normalization
        original_address = address_obj.input_address
        
        logger.info(f"[JENNA_COOPER_LA] Using address for search: '{address_to_search}'")
        logger.info(f"[JENNA_COOPER_LA] Original input address: '{original_address}'")
        
        # Strategy 1: Try Jenna Cooper LA predictive search by title (if provided)
        if title:
            logger.info(f"[JENNA_COOPER_LA] Strategy 1: Trying Jenna Cooper LA predictive search by title: '{title}'")
            result = self._try_jenna_cooper_predictive_search_by_title(title)
            if result:
                logger.success(f"[JENNA_COOPER_LA] SUCCESS: Found property via title search for title: '{title}'")
                return result
            else:
                logger.warning(f"[JENNA_COOPER_LA] Strategy 1 (title search) failed for title: '{title}'")
        
        # Strategy 2: Try Jenna Cooper LA predictive search by address
        logger.info(f"[JENNA_COOPER_LA] Strategy 2: Trying Jenna Cooper LA predictive search by address")
        result = self._try_jenna_cooper_predictive_search(address_to_search, original_address)
        if result:
            logger.success(f"[JENNA_COOPER_LA] SUCCESS: Found property via predictive search for address: '{address_to_search}'")
            return result
        else:
            logger.warning(f"[JENNA_COOPER_LA] Strategy 2 failed for address: '{address_to_search}'")
        
        # Strategy 3: Try direct property URL construction
        logger.info(f"[JENNA_COOPER_LA] Strategy 3: Trying direct property URL construction")
        result = self._try_direct_property_url(address_to_search)
        if result:
            logger.success(f"[JENNA_COOPER_LA] SUCCESS: Found property via direct URL for address: '{address_to_search}'")
            return result
        else:
            logger.warning(f"[JENNA_COOPER_LA] Strategy 3 failed for address: '{address_to_search}'")
        
        # Strategy 4: Try full address format with "ROAD" (no abbreviations)
        logger.info(f"[JENNA_COOPER_LA] Strategy 4: Trying full address format with ROAD (no abbreviations)")
        result = self._try_full_address_format(address_to_search)
        if result:
            logger.success(f"[JENNA_COOPER_LA] SUCCESS: Found property via full address format for address: '{address_to_search}'")
            return result
        else:
            logger.warning(f"[JENNA_COOPER_LA] Strategy 4 failed for address: '{address_to_search}'")
                
        logger.error(f"[JENNA_COOPER_LA] FAILED: No property found for any search strategy")
        logger.error(f"[JENNA_COOPER_LA] Tried addresses: {list(address_obj.plausible_address_matches())}")
        if title:
            logger.error(f"[JENNA_COOPER_LA] Tried title: '{title}'")
        return None
    
    def search_by_title(self, title: str) -> PropertyModel.MLSInfo:
        """Search for property by title (for Jenna Cooper LA tenants)"""
        
        logger.info(f"[JENNA_COOPER_LA] Starting title search for: '{title}'")
        
        # Strategy 1: Try direct URL approach
        logger.info(f"[JENNA_COOPER_LA] Strategy 1: Trying direct URL approach for title: '{title}'")
        result = self._try_direct_url_by_title(title)
        if result:
            logger.success(f"[JENNA_COOPER_LA] SUCCESS: Found property via direct URL for title: '{title}'")
            return result
        else:
            logger.warning(f"[JENNA_COOPER_LA] Strategy 1 (direct URL) failed for title: '{title}'")
        
        # Strategy 2: Try predictive search by title
        logger.info(f"[JENNA_COOPER_LA] Strategy 2: Trying predictive search for title: '{title}'")
        result = self._try_jenna_cooper_predictive_search_by_title(title)
        if result:
            logger.success(f"[JENNA_COOPER_LA] SUCCESS: Found property via predictive search for title: '{title}'")
            return result
        else:
            logger.warning(f"[JENNA_COOPER_LA] Strategy 2 (predictive search) failed for title: '{title}'")
        
        logger.error(f"[JENNA_COOPER_LA] FAILED: No property found for title: '{title}'")
        return None
    
    def _try_jenna_cooper_predictive_search(self, address: str, original_address: str) -> PropertyModel.MLSInfo:
        """Use Jenna Cooper LA's predictive search endpoint to find properties"""
        logger.info(f"[JENNA_COOPER_LA] _try_jenna_cooper_predictive_search called with address: '{address}'")
        # Extract key search terms from the address
        search_terms = set()
        # All abbreviation variants for the full address
        for variant in generate_all_abbreviation_variants(address):
            search_terms.add(variant)
        # All abbreviation variants for the original input address
        for variant in generate_all_abbreviation_variants(original_address):
            search_terms.add(variant)
        # Street address only (first part before comma)
        address_parts = address.split(',')
        if len(address_parts) >= 1:
            street = address_parts[0].strip()
            for variant in generate_all_abbreviation_variants(street):
                search_terms.add(variant)
        # Also add normalized terms from the original input address
        normalized_terms = self._normalize_address_for_jenna_cooper(original_address)
        for norm in normalized_terms:
            for variant in generate_all_abbreviation_variants(norm):
                search_terms.add(variant)
        logger.info(f"[JENNA_COOPER_LA] Final predictive search terms: {list(search_terms)}")
        for search_term in search_terms:
            logger.info(f"[JENNA_COOPER_LA] Trying search term: '{search_term}'")
            search_url = f"https://jennacooperla.com/search/suggest?q={quote_plus(search_term)}&section_id=sections--18776913772799__search-drawer&resources[limit]=10&resources[limit_scope]=each"
            logger.info(f"[JENNA_COOPER_LA] Predictive search URL: {search_url}")
            try:
                response = self._scrape_with_scrapfly(search_url)
                property_links = response.selector.css("a[href*='/pages/']::attr(href)").getall()
                logger.info(f"[JENNA_COOPER_LA] Found {len(property_links)} property links in search results")
                if len(property_links) == 0:
                    logger.warning(f"[JENNA_COOPER_LA] No property links found for search term: '{search_term}'")
                    continue
                best_match_url = None
                best_match_score = 0
                for i, link in enumerate(property_links):
                    link_text = response.selector.css(f"a[href='{link}'] span::text").get()
                    if link_text:
                        logger.info(f"[JENNA_COOPER_LA] Property {i+1}: {link_text}")
                        from difflib import SequenceMatcher
                        def normalize(s):
                            return ''.join(e for e in s.lower() if e.isalnum())
                        norm_search_address = normalize(address)
                        norm_link_text = normalize(link_text)
                        normalized_link_text = self._normalize_address_for_jenna_cooper(link_text)
                        if normalized_link_text:
                            norm_normalized_link = normalize(normalized_link_text[0])
                        else:
                            norm_normalized_link = norm_link_text
                        similarity_original = SequenceMatcher(None, norm_search_address, norm_link_text).ratio()
                        similarity_normalized = SequenceMatcher(None, norm_search_address, norm_normalized_link).ratio()
                        similarity = max(similarity_original, similarity_normalized)
                        logger.info(f"[JENNA_COOPER_LA] Property {i+1} similarity: {similarity:.3f} (original: {similarity_original:.3f}, normalized: {similarity_normalized:.3f})")
                        if similarity > best_match_score:
                            best_match_score = similarity
                            best_match_url = link
                            logger.info(f"[JENNA_COOPER_LA] New best match: {link_text} (similarity: {similarity:.3f})")
                if best_match_url:
                    full_url = f"https://jennacooperla.com{best_match_url}" if best_match_url.startswith('/') else best_match_url
                    logger.info(f"[JENNA_COOPER_LA] Selected best matching property: {full_url} (similarity: {best_match_score:.3f})")
                else:
                    first_property_link = property_links[0]
                    full_url = f"https://jennacooperla.com{first_property_link}" if first_property_link.startswith('/') else first_property_link
                    logger.info(f"[JENNA_COOPER_LA] Fallback to first property: {full_url}")
                result = self._extract_from_property_page(full_url)
                if result:
                    logger.success(f"[JENNA_COOPER_LA] SUCCESS: Extracted property data from predictive search")
                    return result
                else:
                    logger.warning(f"[JENNA_COOPER_LA] Failed to extract data from selected property page")
                    continue
            except Exception as e:
                logger.exception(f"[JENNA_COOPER_LA] Predictive search failed for term '{search_term}': {str(e)}")
                continue
        logger.warning(f"[JENNA_COOPER_LA] All search terms failed for address: '{address}'")
        return None
    
    def _try_jenna_cooper_predictive_search_by_title(self, title: str) -> PropertyModel.MLSInfo:
        """Use Jenna Cooper LA's predictive search endpoint to find properties by title"""
        
        logger.info(f"[JENNA_COOPER_LA] _try_jenna_cooper_predictive_search_by_title called with title: '{title}'")
        
        # Construct the predictive search URL for title search
        search_url = f"https://jennacooperla.com/search/suggest?q={quote_plus(title)}&section_id=sections--18776913772799__search-drawer&resources[limit]=10&resources[limit_scope]=each"
        
        logger.info(f"[JENNA_COOPER_LA] Predictive search URL for title: {search_url}")
        
        try:
            response = self._scrape_with_scrapfly(search_url)
            
            # Look for property links in the "Pages" tab
            property_links = response.selector.css("a[href*='/pages/']::attr(href)").getall()
            logger.info(f"[JENNA_COOPER_LA] Found {len(property_links)} property links in title search results")
            
            if len(property_links) == 0:
                logger.warning(f"[JENNA_COOPER_LA] No property links found for title: '{title}'")
                return None
            
            # Find the best matching property by comparing addresses
            best_match_url = None
            best_match_score = 0
            
            for i, link in enumerate(property_links):
                # Extract address from the URL or link text
                link_text = response.selector.css(f"a[href='{link}'] span::text").get()
                if link_text:
                    logger.info(f"[JENNA_COOPER_LA] Property {i+1} (title search): {link_text}")
                    
                    # Calculate similarity score with address normalization
                    from difflib import SequenceMatcher
                    def normalize(s):
                        return ''.join(e for e in s.lower() if e.isalnum())
                    
                    # Normalize both the search title and the link text
                    norm_search_title = normalize(title)
                    norm_link_text = normalize(link_text)
                    
                    # Also try with address normalization for better matching
                    normalized_link_text = self._normalize_address_for_jenna_cooper(link_text)
                    if normalized_link_text:
                        norm_normalized_link = normalize(normalized_link_text[0])  # Use first normalized version
                    else:
                        norm_normalized_link = norm_link_text
                    
                    # Calculate similarity with both original and normalized versions
                    similarity_original = SequenceMatcher(None, norm_search_title, norm_link_text).ratio()
                    similarity_normalized = SequenceMatcher(None, norm_search_title, norm_normalized_link).ratio()
                    
                    # Use the better similarity score
                    similarity = max(similarity_original, similarity_normalized)
                    
                    logger.info(f"[JENNA_COOPER_LA] Property {i+1} (title search) similarity: {similarity:.3f} (original: {similarity_original:.3f}, normalized: {similarity_normalized:.3f})")
                    
                    if similarity > best_match_score:
                        best_match_score = similarity
                        best_match_url = link
                        logger.info(f"[JENNA_COOPER_LA] New best match (title search): {link_text} (similarity: {similarity:.3f})")
            
            if best_match_url:
                full_url = f"https://jennacooperla.com{best_match_url}" if best_match_url.startswith('/') else best_match_url
                logger.info(f"[JENNA_COOPER_LA] Selected best matching property (title search): {full_url} (similarity: {best_match_score:.3f})")
            else:
                # Fallback to first result if no good match found
                first_property_link = property_links[0]
                full_url = f"https://jennacooperla.com{first_property_link}" if first_property_link.startswith('/') else first_property_link
                logger.info(f"[JENNA_COOPER_LA] Fallback to first property (title search): {full_url}")
                
                # Extract property data from the selected property page
                result = self._extract_from_property_page(full_url)
                if result:
                    logger.success(f"[JENNA_COOPER_LA] SUCCESS: Extracted property data from title search")
                    return result
                else:
                    logger.warning(f"[JENNA_COOPER_LA] Failed to extract data from selected property page (title search)")
                    return None
                    
        except Exception as e:
            logger.exception(f"[JENNA_COOPER_LA] Predictive search by title failed for title '{title}': {str(e)}")
            return None
    
    def _try_direct_url_by_title(self, title: str) -> PropertyModel.MLSInfo:
        """Try to access property directly using title as URL slug"""
        
        logger.info(f"[JENNA_COOPER_LA] _try_direct_url_by_title called with title: '{title}'")
        
        # Generate multiple URL slug formats using utility function
        slugs = generate_url_slugs(title)
        
        logger.info(f"[JENNA_COOPER_LA] Generated slugs:")
        for i, slug in enumerate(slugs, 1):
            logger.info(f"  - Format {i}: '{slug}'")
        
        # Try all URL formats, including all abbreviation variants
        direct_urls = [f"https://jennacooperla.com/pages/{slug}" for slug in slugs]
        for variant in generate_all_abbreviation_variants(title):
            if variant != title:
                variant_slugs = generate_url_slugs(variant)
                direct_urls += [f"https://jennacooperla.com/pages/{slug}" for slug in variant_slugs]
        
        for direct_url in direct_urls:
            logger.info(f"[JENNA_COOPER_LA] Trying direct URL: {direct_url}")
            
            try:
                result = self._extract_from_property_page(direct_url)
                if result:
                    logger.success(f"[JENNA_COOPER_LA] SUCCESS: Found property via direct URL: {direct_url}")
                    return result
                else:
                    logger.warning(f"[JENNA_COOPER_LA] Direct URL returned no data: {direct_url}")
                    
            except Exception as e:
                logger.error(f"[JENNA_COOPER_LA] Direct URL {direct_url} failed: {str(e)}")
                continue
        
        logger.warning(f"[JENNA_COOPER_LA] All direct URL formats failed for title: '{title}'")
        return None
    
    def _extract_search_terms(self, address: str) -> list:
        terms = set()
        address_parts = address.split(',')
        # Generate all abbreviation variants for the full address
        for variant in generate_all_abbreviation_variants(address):
            terms.add(variant)
        # Add street address + city
        if len(address_parts) >= 2:
            street_city = ','.join(address_parts[:2]).strip()
            for variant in generate_all_abbreviation_variants(street_city):
                terms.add(variant)
        # Add just the street address
        if len(address_parts) >= 1:
            street = address_parts[0].strip()
            for variant in generate_all_abbreviation_variants(street):
                terms.add(variant)
        # Add city name
        if len(address_parts) >= 2:
            city = address_parts[1].strip()
            for variant in generate_all_abbreviation_variants(city):
                terms.add(variant)
        # Add street number and name
        if len(address_parts) >= 1:
            street_parts = address_parts[0].strip().split()
            if len(street_parts) >= 2:
                street_number = street_parts[0]
                street_name = ' '.join(street_parts[1:])
                for variant in generate_all_abbreviation_variants(f"{street_number} {street_name}"):
                    terms.add(variant)
                for variant in generate_all_abbreviation_variants(street_name):
                    terms.add(variant)
        # Add normalized versions with abbreviations for Jenna Cooper LA format
        normalized_terms = self._normalize_address_for_jenna_cooper(address)
        for norm in normalized_terms:
            for variant in generate_all_abbreviation_variants(norm):
                terms.add(variant)
        logger.info(f"[JENNA_COOPER_LA] Extracted search terms: {list(terms)}")
        return list(terms)
    
    def _normalize_address_for_jenna_cooper(self, address: str) -> list:
        """Normalize address to match Jenna Cooper LA's abbreviated format"""
        normalized_terms = []
        
        # Apply street abbreviations using the utility function
        normalized_address = apply_street_abbreviations(address)
        normalized_terms.append(normalized_address)
        
        # Normalize street address part
        address_parts = address.split(',')
        if len(address_parts) >= 1:
            street_address = address_parts[0].strip()
            normalized_street = apply_street_abbreviations(street_address)
            normalized_terms.append(normalized_street)
            
            # Also add street number + normalized street name
            street_parts = street_address.split()
            if len(street_parts) >= 2:
                street_number = street_parts[0]
                street_name = ' '.join(street_parts[1:])
                normalized_street_name = apply_street_abbreviations(street_name)
                normalized_terms.append(f"{street_number} {normalized_street_name}")
        
        logger.info(f"[JENNA_COOPER_LA] Normalized address terms: {normalized_terms}")
        return normalized_terms
    
    def _try_direct_property_url(self, address: str) -> PropertyModel.MLSInfo:
        """Try to construct and access direct property URLs based on address patterns, using all abbreviation variants."""
        logger.info(f"[JENNA_COOPER_LA] _try_direct_property_url called with address: '{address}'")
        address_parts = address.split(',')
        if len(address_parts) < 1:
            logger.warning(f"[JENNA_COOPER_LA] Address format invalid: '{address}'")
            return None
        street_address = address_parts[0].strip()
        logger.info(f"[JENNA_COOPER_LA] Trying direct URL construction for street address: '{street_address}'")
        # Try all abbreviation variants for the street address
        slug_variants = set()
        for variant in generate_all_abbreviation_variants(street_address):
            for slug in generate_url_slugs(variant):
                slug_variants.add(slug)
        logger.info(f"[JENNA_COOPER_LA] All slug variants for direct URL: {list(slug_variants)}")
        for slug in slug_variants:
            url = f"https://jennacooperla.com/pages/{slug}"
            logger.info(f"[JENNA_COOPER_LA] Trying direct URL: {url}")
            try:
                result = self._extract_from_property_page(url)
                if result:
                    logger.success(f"[JENNA_COOPER_LA] SUCCESS: Found property via direct URL: {url}")
                    return result
                else:
                    logger.warning(f"[JENNA_COOPER_LA] Direct URL returned no data: {url}")
            except Exception as e:
                logger.error(f"[JENNA_COOPER_LA] Direct URL {url} failed: {str(e)}")
                continue
        logger.warning(f"[JENNA_COOPER_LA] All direct URL strategies failed for address: '{address}'")
        return None
    
    def _try_full_address_format(self, address: str) -> PropertyModel.MLSInfo:
        """Try searching with full address format using 'ROAD' instead of abbreviations"""
        logger.info(f"[JENNA_COOPER_LA] _try_full_address_format called with address: '{address}'")
        
        # Extract street address (first part before comma)
        address_parts = address.split(',')
        if len(address_parts) < 1:
            logger.warning(f"[JENNA_COOPER_LA] Address format invalid: '{address}'")
            return None
        
        street_address = address_parts[0].strip()
        logger.info(f"[JENNA_COOPER_LA] Extracted street address: '{street_address}'")
        
        # Convert to full format (replace RD with ROAD, etc.)
        full_format_address = self._convert_to_full_format(street_address)
        logger.info(f"[JENNA_COOPER_LA] Full format address: '{full_format_address}'")
        
        # Try predictive search with full format
        search_url = f"https://jennacooperla.com/search/suggest?q={quote_plus(full_format_address)}&section_id=sections--18776913772799__search-drawer&resources[limit]=10&resources[limit_scope]=each"
        logger.info(f"[JENNA_COOPER_LA] Full format search URL: {search_url}")
        
        try:
            response = self._scrape_with_scrapfly(search_url)
            property_links = response.selector.css("a[href*='/pages/']::attr(href)").getall()
            logger.info(f"[JENNA_COOPER_LA] Found {len(property_links)} property links in full format search results")
            
            if len(property_links) == 0:
                logger.warning(f"[JENNA_COOPER_LA] No property links found for full format: '{full_format_address}'")
                return None
            
            # Use the first property link found
            first_property_link = property_links[0]
            full_url = f"https://jennacooperla.com{first_property_link}" if first_property_link.startswith('/') else first_property_link
            logger.info(f"[JENNA_COOPER_LA] Using first property from full format search: {full_url}")
            
            result = self._extract_from_property_page(full_url)
            if result:
                logger.success(f"[JENNA_COOPER_LA] SUCCESS: Extracted property data from full format search")
                return result
            else:
                logger.warning(f"[JENNA_COOPER_LA] Failed to extract data from full format property page")
                return None
                
        except Exception as e:
            logger.exception(f"[JENNA_COOPER_LA] Full format search failed for '{full_format_address}': {str(e)}")
            return None
    
    def _convert_to_full_format(self, street_address: str) -> str:
        """Convert abbreviated street address to full format (RD -> ROAD, etc.)"""
        from utils.str_utils import convert_abbreviations_to_full_format
        
        full_format = convert_abbreviations_to_full_format(street_address)
        logger.info(f"[JENNA_COOPER_LA] Converted '{street_address}' to full format: '{full_format}'")
        return full_format
    
    def _extract_from_property_page(self, property_url: str) -> PropertyModel.MLSInfo:
        """Extract property data from a specific property page"""
        
        try:
            # Use Scrapfly's built-in retry mechanism
            response = self._scrape_with_scrapfly(property_url)
            
            # Strategy 1: Try to extract from JSON data
            property_data = self._extract_property_data_from_page(response.selector)
            
            if property_data:
                return self._extract_listing_info_json(property_data)
            
            # Strategy 2: Extract from HTML structure (fallback)
            return self._extract_from_html_structure_detailed(response.selector, property_url)
                
        except Exception as e:
            error_type = self._classify_error(e)
            logger.error(f"[JENNA_COOPER_LA] Failed to extract from property page {property_url} (error type: {error_type}): {str(e)}")
            
            # For certain error types, we might want to try alternative strategies
            if error_type == 'timeout':
                logger.warning(f"[JENNA_COOPER_LA] Timeout error for {property_url} - this might be a slow server")
            elif error_type == 'not_found':
                logger.warning(f"[JENNA_COOPER_LA] Property page not found: {property_url}")
            elif error_type == 'forbidden':
                logger.warning(f"[JENNA_COOPER_LA] Access forbidden for: {property_url}")
            
        return None
    
    def _extract_from_html_structure_detailed(self, selector, property_url: str) -> PropertyModel.MLSInfo:
        """Extract property data from HTML structure with detailed parsing"""
        
        try:
            # Extract address from HTML
            address_element = selector.css("h1::text, .property-title::text, [class*='title']::text").getall()
            if address_element:
                address_text = ''.join(address_element).strip()
            else:
                address_text = ""
            
            # Extract price
            price_element = selector.css("[class*='price'], [class*='Price']::text").getall()
            price_text = ''.join(price_element).strip() if price_element else ""
            
            # Extract description - Target the specific Jenna Cooper LA structure
            # Based on the HTML structure: <span class="old_text"><p>description text...</p></span>
            desc_selectors = [
                ".house_property_details .old_text p::text",  # Primary: exact match to the structure
                ".house_property_details .old_text::text",   # Fallback: get text from span
                "[class*='house_property_details'] .old_text p::text",
                "[class*='house_property_details'] .old_text::text",
                ".old_text p::text",  # Broader fallback
                ".old_text::text",    # Even broader fallback
                "[class*='description'], [class*='Description']::text"  # Generic fallback
            ]
            
            description_text = ""
            for desc_selector in desc_selectors:
                desc_elements = selector.css(desc_selector).getall()
                if desc_elements:
                    description_text = ' '.join(desc_elements).strip()
                    logger.info(f"[JENNA_COOPER_LA] Found description using selector: {desc_selector}")
                    logger.info(f"[JENNA_COOPER_LA] Description preview: {description_text[:100]}...")
                    break
            
            # Extract images - Enhanced image extraction for Jenna Cooper LA
            image_urls = self._extract_images_from_jenna_cooper_page(selector, property_url)
            
            # Extract specifications - Enhanced for Jenna Cooper LA structure
            specs = {}
            
            # Extract property title and status from the specific structure
            # Based on HTML: <h2>SHERMAN OAKS</h2> and <h3>JUST LISTED | $5,399,000</h3>
            property_title_selectors = [
                ".house_property_details h2::text",
                "[class*='house_property_details'] h2::text",
                "h2::text"
            ]
            
            property_title = ""
            for title_selector in property_title_selectors:
                title_elements = selector.css(title_selector).getall()
                if title_elements:
                    property_title = ' '.join(title_elements).strip()
                    logger.info(f"[JENNA_COOPER_LA] Found property title: {property_title}")
                    break
            
            # Extract price and status from h3
            price_status_selectors = [
                ".house_property_details h3::text",
                "[class*='house_property_details'] h3::text",
                "h3::text"
            ]
            
            price_status_text = ""
            for price_selector in price_status_selectors:
                price_elements = selector.css(price_selector).getall()
                if price_elements:
                    price_status_text = ' '.join(price_elements).strip()
                    logger.info(f"[JENNA_COOPER_LA] Found price/status: {price_status_text}")
                    break
            
            # Extract specifications from h4
            # Based on HTML: <h4>6 BEDS | 5.5 BATHS |  POOL | 4,696 SF</h4>
            specs_selectors = [
                ".house_property_details h4::text",
                "[class*='house_property_details'] h4::text",
                "h4::text"
            ]
            
            specs_text = ""
            for specs_selector in specs_selectors:
                specs_elements = selector.css(specs_selector).getall()
                if specs_elements:
                    specs_text = ' '.join(specs_elements).strip()
                    logger.info(f"[JENNA_COOPER_LA] Found specs: {specs_text}")
                    break
            
            # Parse specifications from the text
            if specs_text:
                # Extract beds
                beds_match = re.search(r'(\d+)\s+BEDS?', specs_text, re.IGNORECASE)
                if beds_match:
                    specs['beds'] = int(beds_match.group(1))
                    logger.info(f"[JENNA_COOPER_LA] Extracted beds: {specs['beds']}")
                
                # Extract baths
                baths_match = re.search(r'(\d+(?:\.\d+)?)\s+BATHS?', specs_text, re.IGNORECASE)
                if baths_match:
                    specs['bath'] = float(baths_match.group(1))
                    logger.info(f"[JENNA_COOPER_LA] Extracted baths: {specs['bath']}")
                
                # Extract square footage
                sqft_match = re.search(r'(\d+(?:,\d+)?)\s*SF', specs_text, re.IGNORECASE)
                if sqft_match:
                    specs['living_size'] = int(sqft_match.group(1).replace(',', ''))
                    logger.info(f"[JENNA_COOPER_LA] Extracted square footage: {specs['living_size']}")
                
                # Extract property features (like POOL)
                features = re.findall(r'\|\s*([A-Z\s]+)', specs_text)
                if features:
                    specs['features'] = [feature.strip() for feature in features if feature.strip()]
                    logger.info(f"[JENNA_COOPER_LA] Extracted features: {specs['features']}")
            
            # Fallback to generic selectors if specific structure not found
            if not specs:
                # Look for beds/bathrooms in various formats
                beds_text = selector.css("[class*='bed'], [class*='Bed']::text").getall()
                if beds_text:
                    beds_match = ''.join(beds_text)
                    # Extract number from text like "4 Beds" or "4BR"
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
                logger.info(f"Jenna Cooper LA: Found {len(image_urls)} images, address: {address_text[:50]}...")
                
                # Enhance description with property details for better narration
                enhanced_description = description_text
                if property_title or price_status_text or specs_text:
                    enhanced_parts = []
                    if property_title:
                        enhanced_parts.append(f"Location: {property_title}")
                    if price_status_text:
                        enhanced_parts.append(f"Status and Price: {price_status_text}")
                    if specs_text:
                        enhanced_parts.append(f"Property Details: {specs_text}")
                    if description_text:
                        enhanced_parts.append(f"Description: {description_text}")
                    
                    enhanced_description = " | ".join(enhanced_parts)
                    logger.info(f"[JENNA_COOPER_LA] Enhanced description for narration: {enhanced_description[:200]}...")
                
                return PropertyModel.MLSInfo(
                    mls_id=None,  # We don't have MLS ID from HTML
                    list_price=price_text if price_text else None,
                    description=enhanced_description if enhanced_description else None,
                    specs=specs,
                    media_urls=image_urls,
                )
                
        except Exception as e:
            logger.debug(f"HTML extraction failed: {str(e)}")
            
        return None
    
    def _parse_srcset_urls(self, srcset: str) -> list:
        """Parse srcset attribute and extract individual image URLs, prioritizing highest resolution"""
        urls = []
        if not srcset:
            return urls
            
        try:
            logger.debug(f"[JENNA_COOPER_LA] Parsing srcset: {srcset[:100]}...")
            # Parse srcset format: "url1 width1, url2 width2, ..."
            srcset_parts = srcset.split(',')
            
            # Track URLs with their widths for prioritization
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
                            width_match = re.search(r'(\d+)', width_str)
                            if width_match:
                                width = int(width_match.group(1))
                                url_width_pairs.append((url, width))
                                logger.debug(f"[JENNA_COOPER_LA] Extracted URL from srcset: {url} (width: {width})")
                            else:
                                # If no width found, assume it's a valid URL
                                url_width_pairs.append((url, 0))
                                logger.debug(f"[JENNA_COOPER_LA] Extracted URL from srcset (no width): {url}")
            
            # Sort by width (highest first) and extract URLs
            url_width_pairs.sort(key=lambda x: x[1], reverse=True)
            
            # Take only the highest resolution version of each unique base URL
            seen_base_urls = set()
            for url, width in url_width_pairs:
                # Extract base URL without width parameters
                base_url = re.sub(r'&width=\d+', '', url)
                if base_url not in seen_base_urls:
                    urls.append(url)
                    seen_base_urls.add(base_url)
                    logger.debug(f"[JENNA_COOPER_LA] Selected highest resolution: {url} (width: {width})")
            
            logger.info(f"[JENNA_COOPER_LA] Parsed {len(urls)} unique high-resolution URLs from srcset")
        except Exception as e:
            logger.warning(f"[JENNA_COOPER_LA] Failed to parse srcset: {str(e)}")
            
        return urls
    
    def _extract_with_playwright_gallery(self, property_url: str) -> list:
        """Extract images using Playwright by loading the gallery and extracting all .xo-gallery .swiper-slide img URLs."""
        try:
            from playwright.sync_api import sync_playwright
            logger.info(f"[JENNA_COOPER_LA] Starting Playwright gallery extraction for: {property_url}")
            image_urls = []
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(property_url, timeout=20000)
                # Wait for gallery images to load
                page.wait_for_selector(".xo-gallery .swiper-slide img", timeout=10000)
                img_elements = page.query_selector_all(".xo-gallery .swiper-slide img")
                for img_elem in img_elements:
                    src = img_elem.get_attribute("src")
                    if src and src.startswith("//"):
                        src = f"https:{src}"
                    if src and src.startswith("http") and src not in image_urls:
                        image_urls.append(src)
                browser.close()
            logger.info(f"[JENNA_COOPER_LA] Playwright gallery extraction complete: {len(image_urls)} images")
            return image_urls
        except Exception as e:
            logger.warning(f"[JENNA_COOPER_LA] Playwright extraction failed: {str(e)}")
            return []

    def _extract_images_from_jenna_cooper_page(self, selector, property_url: str = None) -> list:
        """Extract property images from Jenna Cooper LA property page, preferring Playwright if available."""
        # Try Playwright first if property_url is provided
        if property_url:
            pw_images = self._extract_with_playwright_gallery(property_url)
            if pw_images and len(pw_images) >= 5:
                logger.info(f"[JENNA_COOPER_LA] Using Playwright-extracted gallery images: {len(pw_images)}")
                return pw_images
            else:
                logger.info(f"[JENNA_COOPER_LA] Playwright extraction returned too few images, falling back to static extraction.")
        # Strategy 1: Target the Photo Gallery section specifically - Swiper carousel structure
        swiper_gallery_selectors = [
            ".swiper-slide .imagebox__media img::attr(srcset)",
            ".swiper-slide .imagebox__media img::attr(data-srcset)",
            ".swiper-wrapper .swiper-slide .imagebox__media img::attr(srcset)",
            ".swiper-wrapper .swiper-slide .imagebox__media img::attr(data-srcset)",
            "[class*='swiper-slide'] [class*='imagebox__media'] img::attr(srcset)",
            "[class*='swiper-slide'] [class*='imagebox__media'] img::attr(data-srcset)",
            # Fallback to src attributes
            ".swiper-slide .imagebox__media img::attr(src)",
            ".swiper-slide .imagebox__media img::attr(data-src)",
            ".swiper-wrapper .swiper-slide .imagebox__media img::attr(src)",
            ".swiper-wrapper .swiper-slide .imagebox__media img::attr(data-src)",
            "[class*='swiper-slide'] [class*='imagebox__media'] img::attr(src)",
            "[class*='swiper-slide'] [class*='imagebox__media'] img::attr(data-src)"
        ]
        for selector_pattern in swiper_gallery_selectors:
            gallery_images = selector.css(selector_pattern).getall()
            if gallery_images:
                logger.info(f"[JENNA_COOPER_LA] Found {len(gallery_images)} Swiper gallery images with selector: {selector_pattern}")
                for img in gallery_images:
                    if img and img.startswith('//'):
                        img = f"https:{img}"
                    if img and img.startswith('http'):
                        if any(skip_keyword in img.lower() for skip_keyword in ['logo', 'icon', 'avatar', 'profile', 'button', 'banner', 'navmenu', 'frame', 'rectangle', 'compass']):
                            continue
                        if any(include_keyword in img.lower() for include_keyword in ['property', 'listing', 'photo', 'image', 'jennacooperla', 'cdn', 'shop', 'croft', 'neustadt', 'virtually_here_studios']):
                            image_urls.append(img)
                    elif img and ',' in img and 'w' in img:
                        parsed_urls = self._parse_srcset_urls(img)
                        for url in parsed_urls:
                            if any(skip_keyword in url.lower() for skip_keyword in ['logo', 'icon', 'avatar', 'profile', 'button', 'banner', 'navmenu', 'frame', 'rectangle', 'compass']):
                                continue
                            if any(include_keyword in url.lower() for include_keyword in ['property', 'listing', 'photo', 'image', 'jennacooperla', 'cdn', 'shop', 'croft', 'neustadt', 'virtually_here_studios']):
                                image_urls.append(url)
        xo_gallery_images = _extract_images_from_xo_gallery(selector)
        image_urls.extend(xo_gallery_images)
        # Strategy 2: Target the Photo Gallery section with broader selectors (fallback)
        photo_gallery_selectors = [
            ".shopify-section--apps img::attr(srcset)",
            ".shopify-section--apps img::attr(data-srcset)",
            "[class*='shopify-section'][class*='apps'] img::attr(srcset)",
            "[class*='shopify-section'][class*='apps'] img::attr(data-srcset)",
            ".shopify-section.shopify-section--apps img::attr(srcset)",
            ".shopify-section.shopify-section--apps img::attr(data-srcset)",
            ".xo-gallery img::attr(srcset)",
            ".xo-gallery img::attr(data-srcset)",
            "[class*='xo-gallery'] img::attr(srcset)",
            "[class*='xo-gallery'] img::attr(data-srcset)",
            # Fallback to src attributes
            ".shopify-section--apps img::attr(src)",
            ".shopify-section--apps img::attr(data-src)",
            "[class*='shopify-section'][class*='apps'] img::attr(src)",
            "[class*='shopify-section'][class*='apps'] img::attr(data-src)",
            ".shopify-section.shopify-section--apps img::attr(src)",
            ".shopify-section.shopify-section--apps img::attr(data-src)",
            ".xo-gallery img::attr(src)",
            ".xo-gallery img::attr(data-src)",
            "[class*='xo-gallery'] img::attr(src)",
            "[class*='xo-gallery'] img::attr(data-src)"
        ]
        for selector_pattern in photo_gallery_selectors:
            gallery_images = selector.css(selector_pattern).getall()
            if gallery_images:
                logger.info(f"[JENNA_COOPER_LA] Found {len(gallery_images)} gallery images with selector: {selector_pattern}")
                for img in gallery_images:
                    if img and img.startswith('//'):
                        img = f"https:{img}"
                    if img and img.startswith('http'):
                        if any(skip_keyword in img.lower() for skip_keyword in ['logo', 'icon', 'avatar', 'profile', 'button', 'banner', 'navmenu', 'frame', 'rectangle', 'compass']):
                            continue
                        if any(include_keyword in img.lower() for include_keyword in ['property', 'listing', 'photo', 'image', 'jennacooperla', 'cdn', 'shop', 'croft', 'neustadt', 'virtually_here_studios']):
                            image_urls.append(img)
                    elif img and ',' in img and 'w' in img:
                        parsed_urls = self._parse_srcset_urls(img)
                        for url in parsed_urls:
                            if any(skip_keyword in url.lower() for skip_keyword in ['logo', 'icon', 'avatar', 'profile', 'button', 'banner', 'navmenu', 'frame', 'rectangle', 'compass']):
                                continue
                            if any(include_keyword in url.lower() for include_keyword in ['property', 'listing', 'photo', 'image', 'jennacooperla', 'cdn', 'shop', 'croft', 'neustadt', 'virtually_here_studios']):
                                image_urls.append(url)
        # Strategy 3: Extract images from Shopify CDN (fallback)
        shopify_selectors = [
            "img[src*='jennacooperla.com/cdn/shop']::attr(srcset)",
            "img[src*='jennacooperla.com/cdn/shop']::attr(data-srcset)",
            "[class*='gallery'] img::attr(srcset)",
            "[class*='gallery'] img::attr(data-srcset)",
            "[class*='image'] img::attr(srcset)",
            "[class*='image'] img::attr(data-srcset)",
            "[class*='photo'] img::attr(srcset)",
            "[class*='photo'] img::attr(data-srcset)",
            # Fallback to src attributes
            "img[src*='jennacooperla.com/cdn/shop']::attr(src)",
            "img[src*='jennacooperla.com/cdn/shop']::attr(data-src)",
            "[class*='gallery'] img::attr(src)",
            "[class*='gallery'] img::attr(data-src)",
            "[class*='image'] img::attr(src)",
            "[class*='image'] img::attr(data-src)",
            "[class*='photo'] img::attr(src)",
            "[class*='photo'] img::attr(data-src)"
        ]
        for selector_pattern in shopify_selectors:
            shopify_images = selector.css(selector_pattern).getall()
            if shopify_images:
                logger.info(f"[JENNA_COOPER_LA] Found {len(shopify_images)} Shopify images with selector: {selector_pattern}")
                for img in shopify_images:
                    if img and img.startswith('//'):
                        img = f"https:{img}"
                    if img and img.startswith('http'):
                        if any(skip_keyword in img.lower() for skip_keyword in ['logo', 'icon', 'avatar', 'profile', 'button', 'banner', 'navmenu', 'frame', 'rectangle', 'compass']):
                            continue
                        if any(include_keyword in img.lower() for include_keyword in ['property', 'listing', 'photo', 'image', 'jennacooperla', 'cdn', 'shop', 'croft', 'neustadt', 'virtually_here_studios']):
                            image_urls.append(img)
                    elif img and ',' in img and 'w' in img:
                        parsed_urls = self._parse_srcset_urls(img)
                        for url in parsed_urls:
                            if any(skip_keyword in url.lower() for skip_keyword in ['logo', 'icon', 'avatar', 'profile', 'button', 'banner', 'navmenu', 'frame', 'rectangle', 'compass']):
                                continue
                            if any(include_keyword in url.lower() for include_keyword in ['property', 'listing', 'photo', 'image', 'jennacooperla', 'cdn', 'shop', 'croft', 'neustadt', 'virtually_here_studios']):
                                image_urls.append(url)
        # Strategy 4: Extract images from srcset attributes (fallback)
        srcset_selectors = [
            "img::attr(srcset)",
            "[class*='gallery'] img::attr(srcset)",
            "[class*='image'] img::attr(srcset)"
        ]
        for srcset_selector in srcset_selectors:
            srcset_images = selector.css(srcset_selector).getall()
            if srcset_images:
                logger.info(f"[JENNA_COOPER_LA] Found {len(srcset_images)} srcset images with selector: {srcset_selector}")
                for srcset in srcset_images:
                    if srcset:
                        # Parse srcset and extract individual URLs
                        parsed_urls = self._parse_srcset_urls(srcset)
                        for url in parsed_urls:
                            if any(skip_keyword in url.lower() for skip_keyword in ['logo', 'icon', 'avatar', 'profile', 'button', 'banner', 'navmenu', 'frame', 'rectangle', 'compass']):
                                continue
                            if any(include_keyword in url.lower() for include_keyword in ['property', 'listing', 'photo', 'image', 'jennacooperla', 'cdn', 'shop', 'croft', 'neustadt', 'virtually_here_studios']):
                                image_urls.append(url)
        # Remove duplicates and exclude known placeholder/banner images
        EXCLUDE_IMAGE_URLS = [
            "https://jennacooperla.com/cdn/shop/files/IMAGE_1_-_CORRECT_SHOPIFY_SIZE_9bf6c5ec-cdd0-464f-ad3a-12723735ff3d.jpg"
        ]
        normalized_seen = set()
        filtered_images = []
        for img in image_urls:
            img_base = img.split("?")[0].strip()
            if _is_placeholder_image(img):
                logger.info(f"[JENNA_COOPER_LA] Excluding Shopify placeholder/banner image: {img}")
                continue
            if img_base in normalized_seen:
                continue
            normalized_seen.add(img_base)
            if any(skip_keyword in img.lower() for skip_keyword in ['logo', 'icon', 'avatar', 'profile', 'button', 'banner', 'advertisement', 'agent', 'team', 'staff', 'broker', 'navmenu', 'frame', 'rectangle', 'compass', 'product', 'featured_product']):
                logger.debug(f"[JENNA_COOPER_LA] Skipping image due to skip keyword: {img}")
                continue
            if 'cdn.shopify.com' in img or 'jennacooperla.com/cdn/shop' in img:
                if '/files/' in img:
                    logger.debug(f"[JENNA_COOPER_LA] Including Shopify CDN image with /files/: {img}")
                    filtered_images.append(img)
                    continue
            if any(include_keyword in img.lower() for include_keyword in ['property', 'listing', 'photo', 'image', 'jennacooperla', 'cdn', 'shop', 'croft', 'neustadt', 'virtually_here_studios']):
                logger.debug(f"[JENNA_COOPER_LA] Including image with include keyword: {img}")
                filtered_images.append(img)
            else:
                logger.debug(f"[JENNA_COOPER_LA] Skipping image - no include keywords found: {img}")
        logger.info(f"[JENNA_COOPER_LA] Extracted {len(filtered_images)} property images from {len(image_urls)} total images (after deduplication and exclusion)")
        limited_images = filtered_images[:36]
        logger.info(f"[JENNA_COOPER_LA] Limited to {len(limited_images)} images for download")
        return limited_images
    
    def _extract_property_data_from_page(self, selector) -> dict:
        """Extract property data from Jenna Cooper LA search page"""
        
        # Try to find property data in various script tags
        script_selectors = [
            "script[type='application/json']::text",
            "script[data-shopify]::text"
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
        
        # Common paths where property data might be stored in Shopify
        possible_paths = [
            "product",
            "page",
            "article",
            "data.product",
            "data.page",
            "data.article"
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
                property_keys = ['price', 'address', 'bedrooms', 'bathrooms', 'squareFootage', 'images', 'photos', 'title']
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
        """Extract description from HTML element - Enhanced for Jenna Cooper LA structure"""
        desc_selectors = [
            # Jenna Cooper LA specific structure
            ".house_property_details .old_text p::text",
            ".house_property_details .old_text::text",
            "[class*='house_property_details'] .old_text p::text",
            "[class*='house_property_details'] .old_text::text",
            ".old_text p::text",
            ".old_text::text",
            # Generic fallbacks
            ".description::text",
            ".property-description::text",
            ".listing-description::text",
            "[data-description]::attr(data-description)"
        ]
        
        for selector in desc_selectors:
            desc = element.css(selector).get()
            if desc:
                logger.info(f"[JENNA_COOPER_LA] Found description using selector: {selector}")
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
        )

def _extract_images_from_xo_gallery(selector) -> list:
    """Extract all images from the xo-gallery photo gallery section (Jenna Cooper site)."""
    images = []
    img_elems = selector.css('.xo-gallery .swiper-slide img')
    logger.info(f"[JENNA_COOPER_LA] [XO-GALLERY] Found {len(img_elems)} <img> elements in swiper-slide")
    for img_elem in img_elems:
        for attr in ["src", "data-src"]:
            img = img_elem.attrib.get(attr)
            if img and img.startswith('//'):
                img = f"https:{img}"
            if img and img.startswith('http') and img not in images:
                images.append(img)
    logger.info(f"[JENNA_COOPER_LA] [XO-GALLERY] Total images extracted from swiper-slide: {len(images)}")
    return images

# DEPRECATED: Use _extract_images_from_xo_gallery instead
def _extract_images_from_swiper_gallery(selector) -> list:
    return []

# For testing purposes only
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Jenna Cooper LA Scraper')

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
        engine = JennaCooperLA()
        
        mls_info = engine.get_property_info(
            address_obj=address, 
            debug=True if args.debug else False)
        print(mls_info)
                
    except Exception as e:
        logger.exception(e)
        
        
if __name__ == '__main__':
    main() 