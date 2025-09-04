import re
import requests
from bs4 import BeautifulSoup
import json
import jmespath
import argparse
from rich import print
import time

from logger import logger
from config.config import settings
from property.scrapers.scraper_base import ScraperBase
from property.property_model import PropertyModel
from property.address import Address
from property.scrapers.config.config import ScraperConfig

class Compass(ScraperBase):
    def __init__(self):
        pass
    
    def get_property_info(self, address_obj:Address)->PropertyModel.MLSInfo:
        
        logger.info(f"[COMPASS] {self.__class__.__name__} - Fetching listing information for property address : {address_obj.input_address}")

        for address in address_obj.plausible_address_matches():
            
            logger.debug(f"[COMPASS] Attempting to fetch listing from address variation - {address}")
            
            # search listings
            url = "https://www.compass.com/api/v3/omnisuggest/autocomplete"
            payload = {
                "q": address,
                "infoFields": [2],
                "listingTypes": [2],
            }
            
            try:
                response = requests.post(url, headers=self.HEADERS, json=payload)    
                response.raise_for_status()
                extra={
                        "url": url,
                        "status_code": response.status_code,
                        "response_body": response.text
                    }
                logger.debug(
                    f"[COMPASS] HTTP request succeeded\n{extra}"
                )

                response_json = response.json()
                if not jmespath.search('categories', response_json):
                    continue

                # Find exact address match instead of taking the first item
                exact_match = self._find_exact_address_match(address, response_json["categories"][0]["items"])
                if not exact_match:
                    logger.warning(f"[COMPASS] No exact address match found for: {address}")
                    logger.debug(f"[COMPASS] Available addresses: {[item['text'] for item in response_json['categories'][0]['items']]}")
                    continue
                
                logger.info(f"[COMPASS] Found exact address match: {exact_match['text']} (ID: {exact_match['id']})")
                
                url = (
                    "https://www.compass.com"
                    + exact_match["redirectUrl"]
                )
                
                response = requests.get(url, headers=self.HEADERS)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Try multiple methods to extract property data
                property_data = self._extract_property_data(soup, url)
                if property_data:
                    return property_data
                
            except requests.exceptions.HTTPError as he:
                extra={
                        "url": url,
                        "status_code": he.response.status_code,
                        "reason": he.response.reason,
                        "response_body": he.response.text
                    }
                logger.error(
                    f"[COMPASS] HTTP request failed\n{extra}",
                )
                return None
            except ValueError as ve:
                logger.error(f"[COMPASS] {ve}")
                return None
            except Exception as e:
                logger.exception(f"[COMPASS] {e}")
                return None
            
        logger.warning(f"[COMPASS] Compass failed to fetch listing - {address_obj.formatted_address}")
        return None
    
    def _extract_property_data(self, soup: BeautifulSoup, property_url: str = None) -> PropertyModel.MLSInfo:
        """
        Extract property data from the listing page using multiple methods.
        """
        
        # Method 1: Try to extract from __NEXT_DATA__ script tag (NEW PRIORITY)
        property_data = self._extract_from_next_data(soup)
        if property_data:
            # Enhance with Playwright image extraction if we have the property URL
            if property_url:
                logger.info("[COMPASS] Enhancing property data with Playwright image extraction...")
                enhanced_media_urls = self._extract_images_with_playwright(property_url)
                if enhanced_media_urls:
                    logger.info(f"[COMPASS] Playwright found {len(enhanced_media_urls)} high-quality images")
                    property_data.media_urls = enhanced_media_urls
                else:
                    logger.warning("[COMPASS] Playwright image extraction failed, using original images")
            return property_data
        
        # Method 2: Try to find __PARTIAL_INITIAL_DATA__ script tag
        property_data = self._extract_from_partial_initial_data(soup)
        if property_data:
            return property_data
        
        # Method 3: Try to find other script tags with property data
        property_data = self._extract_from_other_scripts(soup)
        if property_data:
            return property_data
        
        # Method 4: Try to find JSON-LD structured data
        property_data = self._extract_from_json_ld(soup)
        if property_data:
            return property_data
        
        # Method 5: Extract from HTML elements (fallback)
        property_data = self._extract_from_html_elements(soup)
        if property_data:
            return property_data
        
        logger.error("[COMPASS] Could not extract property data using any method")
        return None

    def _extract_from_partial_initial_data(self, soup: BeautifulSoup) -> PropertyModel.MLSInfo:
        """Extract data from __PARTIAL_INITIAL_DATA__ script tag."""
        try:
            script_tag = soup.find("script", string=re.compile(r"window\.__PARTIAL_INITIAL_DATA__"))
            if not script_tag:
                logger.debug("[COMPASS] No __PARTIAL_INITIAL_DATA__ script tag found")
                return None
            
            # Extract the full text of that script
            script_text = script_tag.get_text(strip=True)
            
            # Regex pattern to capture the JSON after __PARTIAL_INITIAL_DATA__
            pattern = r"window\.__(\w+)__\s*=\s*(.*)"
            match = re.search(pattern, script_text, flags=re.DOTALL)
            if not match:
                logger.debug("[COMPASS] Could not extract JSON data from __PARTIAL_INITIAL_DATA__")
                return None

            # The JSON portion
            json_str = match.group(2)
            json_data = json.loads(json_str)
            return self._extract_listing_info_json(json_data=json_data)
            
        except Exception as e:
            logger.debug(f"[COMPASS] Failed to extract from __PARTIAL_INITIAL_DATA__: {str(e)}")
            return None
    
    def _extract_from_other_scripts(self, soup: BeautifulSoup) -> PropertyModel.MLSInfo:
        """Extract data from other script tags with property data."""
        try:
            # Look for script tags containing property data patterns
            script_tags = soup.find_all('script')
            for script in script_tags:
                script_text = script.get_text()
                
                # Look for common property data patterns
                if 'listingRelation' in script_text or 'propertyData' in script_text:
                    # Try to extract JSON from the script
                    json_match = re.search(r'(\{.*\})', script_text, re.DOTALL)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(1))
                            return self._extract_listing_info_json(data)
                        except json.JSONDecodeError:
                            continue
                            
        except Exception as e:
            logger.debug(f"[COMPASS] Failed to extract from other scripts: {str(e)}")
            return None
    
    def _extract_from_json_ld(self, soup: BeautifulSoup) -> PropertyModel.MLSInfo:
        """Extract data from JSON-LD structured data."""
        try:
            script_tags = soup.find_all('script', type='application/ld+json')
            for script in script_tags:
                try:
                    data = json.loads(script.string)
                    if data.get('@type') == 'Product' or data.get('@type') == 'House':
                        return self._parse_json_ld_data(data)
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            logger.debug(f"Failed to extract from JSON-LD: {str(e)}")
            return None
    
    def _extract_from_html_elements(self, soup: BeautifulSoup) -> PropertyModel.MLSInfo:
        """Extract data from HTML elements as a fallback method."""
        try:
            # Extract price
            price_elem = soup.find(['span', 'div'], class_=re.compile(r'price|Price', re.I))
            list_price = price_elem.get_text().strip() if price_elem else None
            
            # Extract description
            desc_elem = soup.find(['div', 'p'], class_=re.compile(r'description|Description', re.I))
            description = desc_elem.get_text().strip() if desc_elem else None
            
            # Extract images with enhanced Compass-specific detection
            media_urls = self._extract_compass_images_from_html(soup)
            
            # Extract specs from various elements
            specs = {}
            
            # Beds
            beds_elem = soup.find(['span', 'div'], string=re.compile(r'\d+\s*bed', re.I))
            if beds_elem:
                beds_match = re.search(r'(\d+)', beds_elem.get_text())
                specs['beds'] = int(beds_match.group(1)) if beds_match else None
            
            # Baths
            bath_elem = soup.find(['span', 'div'], string=re.compile(r'\d+\s*bath', re.I))
            if bath_elem:
                bath_match = re.search(r'(\d+)', bath_elem.get_text())
                specs['bath'] = int(bath_match.group(1)) if bath_match else None
            
            # Square footage
            sqft_elem = soup.find(['span', 'div'], string=re.compile(r'\d+\s*sq\s*ft', re.I))
            if sqft_elem:
                sqft_match = re.search(r'(\d+)', sqft_elem.get_text())
                specs['living_size'] = int(sqft_match.group(1)) if sqft_match else None
            
            if list_price or description or media_urls:
                return PropertyModel.MLSInfo(
                    mls_id=None,  # May not be available from HTML
                    list_price=list_price,
                    description=description,
                    specs=specs,
                    media_urls=media_urls,
                    status="Active" if list_price else None  # Default to Active if has price
                )
                
        except Exception as e:
            logger.debug(f"Failed to extract from HTML elements: {str(e)}")
            return None

    def _extract_compass_images_from_html(self, soup: BeautifulSoup) -> list[str]:
        """Extract high-quality images from Compass HTML with multiple strategies."""
        media_urls = []
        
        try:
            # Strategy 1: Extract from media-gallery container (NEW HIGH PRIORITY)
            media_urls = self._extract_images_from_media_gallery(soup)
            if media_urls and len(media_urls) >= ScraperConfig.MIN_IMAGES_FOR_EARLY_RETURN:
                logger.info(f"[COMPASS] Media gallery strategy found {len(media_urls)} high-quality images (returning early)")
                return media_urls
            elif media_urls:
                logger.info(f"[COMPASS] Media gallery strategy found {len(media_urls)} high-quality images (continuing to other strategies)")
            
            # Strategy 2: Look for Compass-specific image containers
            compass_image_containers = soup.find_all(['div', 'section'], class_=re.compile(r'image|photo|gallery|slide|carousel', re.I))
            for container in compass_image_containers:
                # Look for high-quality image sources
                img_tags = container.find_all('img', src=re.compile(r'\.(jpg|jpeg|png|webp)', re.I))
                for img in img_tags:
                    src = img.get('src')
                    if src and not src.startswith('data:'):
                        # Normalize URL
                        src = self._normalize_compass_url(src)
                        if src and self._is_compass_high_quality_url(src):
                            media_urls.append(src)
            
            # Strategy 3: Look for data attributes that contain high-quality URLs
            data_attributes = ['data-src', 'data-image', 'data-original', 'data-full', 'data-large']
            for attr in data_attributes:
                elements_with_data = soup.find_all(attrs={attr: True})
                for element in elements_with_data:
                    src = element.get(attr)
                    if src and src.startswith('http') and re.search(r'\.(jpg|jpeg|png|webp)', src, re.I):
                        if self._is_compass_high_quality_url(src):
                            media_urls.append(src)
            
            # Strategy 4: Look for background images in CSS with high-quality indicators
            elements_with_bg = soup.find_all(style=re.compile(r'background-image.*url', re.I))
            for element in elements_with_bg:
                style = element.get('style', '')
                bg_matches = re.findall(r'url\(["\']?([^"\')\s]+)["\']?\)', style)
                for match in bg_matches:
                    if re.search(r'\.(jpg|jpeg|png|webp)', match, re.I):
                        match = self._normalize_compass_url(match)
                        if match and self._is_compass_high_quality_url(match):
                            media_urls.append(match)
            
            # Strategy 5: Look for Compass-specific script tags with image data
            script_tags = soup.find_all('script')
            for script in script_tags:
                script_text = script.get_text()
                if 'compass' in script_text.lower() and ('image' in script_text.lower() or 'photo' in script_text.lower()):
                    # Try to extract image URLs from script content
                    image_urls = re.findall(r'https?://[^"\s]+\.(?:jpg|jpeg|png|webp)', script_text, re.I)
                    for url in image_urls:
                        if self._is_compass_high_quality_url(url):
                            media_urls.append(url)
            
            # Strategy 6: Look for JSON-LD structured data with Compass images
            json_ld_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_ld_scripts:
                try:
                    data = json.loads(script.string)
                    if data.get('@type') in ['Product', 'House', 'RealEstateListing']:
                        images = data.get('image', [])
                        if isinstance(images, str):
                            if self._is_compass_high_quality_url(images):
                                media_urls.append(images)
                        elif isinstance(images, list):
                            for img in images:
                                if isinstance(img, str) and self._is_compass_high_quality_url(img):
                                    media_urls.append(img)
                except json.JSONDecodeError:
                    continue
            
            # Strategy 7: Fallback to general image search with quality filtering
            if len(media_urls) < 5:  # If we don't have enough high-quality images
                img_tags = soup.find_all('img', src=re.compile(r'\.(jpg|jpeg|png|webp)', re.I))
                for img in img_tags[:30]:  # Check more images
                    src = img.get('src')
                    if src and not src.startswith('data:'):
                        src = self._normalize_compass_url(src)
                        if src and self._is_compass_high_quality_url(src):
                            media_urls.append(src)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in media_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            
            logger.debug(f"[COMPASS] Extracted {len(unique_urls)} high-quality images from Compass HTML")
            return unique_urls[:ScraperConfig.MAX_IMAGES_PER_PROPERTY]  # Limit to configured max images
            
        except Exception as e:
            logger.error(f"[COMPASS] Error extracting Compass images from HTML: {str(e)}")
            return []

    def _extract_images_from_media_gallery(self, soup: BeautifulSoup) -> list[str]:
        """Extract high-quality images directly from the media-gallery container."""
        try:
            logger.info("[COMPASS] Attempting to extract images from media-gallery container...")
            
            # Find the media-gallery container
            media_gallery = soup.find('div', id='media-gallery')
            if not media_gallery:
                logger.debug("[COMPASS] Media gallery container not found")
                return []
            
            logger.info("[COMPASS] Media gallery container found, extracting images...")
            
            # Find all image elements within the media gallery
            img_elements = media_gallery.find_all('img')
            logger.debug(f"[COMPASS] Found {len(img_elements)} image elements in media gallery")
            
            media_urls = []
            for i, img in enumerate(img_elements):
                # Check for lazy-loaded images first (data-flickity-lazyload-src and data-flickity-lazyload-srcset)
                lazy_src = img.get('data-flickity-lazyload-src')
                lazy_srcset = img.get('data-flickity-lazyload-srcset')
                
                if lazy_srcset:
                    # Parse lazy-loaded srcset to find the highest quality image
                    srcset_urls = self._parse_srcset(lazy_srcset)
                    if srcset_urls:
                        # Look for 1500x1000.webp first (highest quality based on your example)
                        high_res_url = next((url for url in srcset_urls if '1500x1000.webp' in url), None)
                        if high_res_url:
                            media_urls.append(high_res_url)
                            logger.debug(f"[COMPASS] Media gallery lazy-loaded image {i+1}: {high_res_url}")
                            continue
                        # Fallback to origin.webp
                        origin_url = next((url for url in srcset_urls if 'origin.webp' in url), None)
                        if origin_url:
                            media_urls.append(origin_url)
                            logger.debug(f"[COMPASS] Media gallery lazy-loaded image {i+1}: {origin_url}")
                            continue
                        # Fallback to the highest resolution available
                        highest_url = srcset_urls[-1] if srcset_urls else None
                        if highest_url:
                            media_urls.append(highest_url)
                            logger.debug(f"[COMPASS] Media gallery lazy-loaded image {i+1}: {highest_url}")
                            continue
                
                # Fallback to lazy-loaded src
                if lazy_src and not lazy_src.startswith('data:'):
                    lazy_src = self._normalize_compass_url(lazy_src)
                    if lazy_src and self._is_compass_high_quality_url(lazy_src):
                        media_urls.append(lazy_src)
                        logger.debug(f"[COMPASS] Media gallery lazy-loaded image {i+1}: {lazy_src}")
                        continue
                
                # Get the regular src attribute
                src = img.get('src')
                if not src:
                    continue
                
                # Get regular srcset for higher quality images
                srcset = img.get('srcset')
                
                # Prefer srcset with origin.webp if available
                if srcset:
                    # Parse srcset to find the highest quality image
                    srcset_urls = self._parse_srcset(srcset)
                    if srcset_urls:
                        # Look for origin.webp first (highest quality)
                        origin_url = next((url for url in srcset_urls if 'origin.webp' in url), None)
                        if origin_url:
                            media_urls.append(origin_url)
                            logger.debug(f"[COMPASS] Media gallery image {i+1}: {origin_url}")
                            continue
                        # Fallback to the highest resolution available
                        highest_url = srcset_urls[-1] if srcset_urls else None
                        if highest_url:
                            media_urls.append(highest_url)
                            logger.debug(f"[COMPASS] Media gallery image {i+1}: {highest_url}")
                            continue
                
                # Fallback to src attribute
                if src and not src.startswith('data:'):
                    src = self._normalize_compass_url(src)
                    if src and self._is_compass_high_quality_url(src):
                        media_urls.append(src)
                        logger.debug(f"[COMPASS] Media gallery image {i+1}: {src}")
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in media_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            
            logger.info(f"[COMPASS] Media gallery strategy extracted {len(unique_urls)} unique high-quality images")
            logger.debug(f"[COMPASS] Final media gallery URLs: {unique_urls[:3]}...")
            return unique_urls[:ScraperConfig.MAX_IMAGES_PER_PROPERTY]  # Limit to configured max images
            
        except Exception as e:
            logger.error(f"[COMPASS] Error extracting images from media gallery: {str(e)}")
            return []

    def _parse_srcset(self, srcset: str) -> list[str]:
        """Parse srcset attribute to extract URLs in order of resolution."""
        try:
            if not srcset:
                return []
            
            logger.debug(f"[COMPASS] Parsing srcset: {srcset[:200]}...")
            
            # Split srcset by commas and parse each entry
            entries = [entry.strip() for entry in srcset.split(',')]
            parsed_urls = []
            
            for entry in entries:
                # Split by whitespace to separate URL from descriptor
                parts = entry.split()
                if parts:
                    url = parts[0]
                    # Only include URLs that look like image files
                    if re.search(r'\.(jpg|jpeg|png|webp)', url, re.I):
                        # Normalize the URL before adding it
                        normalized_url = self._normalize_compass_url(url)
                        if normalized_url:
                            parsed_urls.append(normalized_url)
                            logger.debug(f"[COMPASS] Added normalized URL from srcset: {normalized_url}")
            
            logger.debug(f"[COMPASS] Parsed {len(parsed_urls)} URLs from srcset")
            
            # Sort by resolution with specific priorities for Compass URLs
            parsed_urls.sort(key=lambda x: (
                # Prioritize 1500x1000.webp (highest quality based on user example)
                '1500x1000.webp' not in x,
                # Then prioritize origin.webp
                'origin.webp' not in x,
                # Then sort by apparent resolution (number in URL)
                -max((int(n) for n in re.findall(r'\d+', x)), default=0)
            ))
            
            logger.debug(f"[COMPASS] Final sorted URLs from srcset: {parsed_urls[:3]}...")
            return parsed_urls
            
        except Exception as e:
            logger.debug(f"[COMPASS] Error parsing srcset: {str(e)}")
            return []

    def _normalize_compass_url(self, url: str) -> str:
        """Normalize Compass URLs to ensure they're complete and accessible."""
        if not url:
            return None
        
        original_url = url
        logger.debug(f"[COMPASS] Normalizing URL: {original_url}")
        
        # Handle protocol-relative URLs (starting with //)
        if url.startswith('//'):
            url = f"https:{url}"
            logger.debug(f"[COMPASS] Converted protocol-relative URL: {original_url} -> {url}")
        
        # Handle relative URLs
        elif url.startswith('/'):
            url = f"https://www.compass.com{url}"
            logger.debug(f"[COMPASS] Converted relative URL: {original_url} -> {url}")
        elif not url.startswith('http'):
            url = f"https://www.compass.com/{url}"
            logger.debug(f"[COMPASS] Converted non-http URL: {original_url} -> {url}")
        
        # Ensure HTTPS
        if url.startswith('http://'):
            url = url.replace('http://', 'https://', 1)
            logger.debug(f"[COMPASS] Converted HTTP to HTTPS: {original_url} -> {url}")
        
        logger.debug(f"[COMPASS] Final normalized URL: {url}")
        return url
    
    def _parse_json_ld_data(self, data: dict) -> PropertyModel.MLSInfo:
        """Parse JSON-LD structured data."""
        try:
            mls_id = data.get('sku') or data.get('mpn')
            list_price = data.get('offers', {}).get('price')
            description = data.get('description')
            
            # Extract images from JSON-LD
            media_urls = []
            images = data.get('image', [])
            if isinstance(images, str):
                media_urls = [images]
            elif isinstance(images, list):
                media_urls = [img for img in images if isinstance(img, str)]
            
            # Extract specs from JSON-LD
            specs = {}
            # JSON-LD may not have detailed specs, so we'll leave them empty
            
            return PropertyModel.MLSInfo(
                mls_id=mls_id,
                list_price=str(list_price) if list_price else None,
                description=description,
                specs=specs,
                media_urls=media_urls,
                status="Active" if list_price else None  # Default to Active if has price
            )
            
        except Exception as e:
            logger.error(f"Failed to parse JSON-LD data: {str(e)}")
            return None
            
    def _extract_listing_info_json(self, json_data:dict)->PropertyModel.MLSInfo:
        listing = jmespath.search('props.listingRelation.listing', json_data) 
        
        mls_id = jmespath.search('externalId', listing)
        list_price = jmespath.search('price.lastKnown', listing)
        description = jmespath.search('description', listing)
        
        # Extract status from various possible locations
        status = (jmespath.search('status', listing) or 
                 jmespath.search('listingStatus', listing) or
                 jmespath.search('mlsStatus', listing) or
                 jmespath.search('state', listing) or
                 jmespath.search('detailedInfo.keyDetails[?key=="Status"].value | [0]', listing) or
                 jmespath.search('detailedInfo.keyDetails[?key=="Listing Status"].value | [0]', listing))
        
        # Default to "Active" if no status found and property has price
        if not status and list_price:
            status = "Active"
        
        # PRIMARY: Use the old approach first (which was working well)
        media_urls = self._extract_media_urls_old_approach(listing)
        
        # FALLBACK: If old approach fails, try the new enhanced approach
        if not media_urls or len(media_urls) == 0:
            logger.warning("Old approach found no images, trying enhanced approach...")
            media_urls = self._extract_media_urls_compass_api(listing)
            if media_urls:
                logger.info(f"Enhanced approach found {len(media_urls)} images")
        
        specs = {}
        specs['property_type'] = jmespath.search("detailedInfo.keyDetails[?key=='Compass Type'].value | [0]", listing)
        specs['beds'] = jmespath.search('size.bedrooms', listing)
        specs['bath'] = jmespath.search('size.bathrooms', listing)
        specs['living_size'] = jmespath.search('size.squareFeet', listing)
        specs['lot_size'] = jmespath.search('size.lotSizeInSquareFeet', listing)
        
        logger.debug(f"Extracted {len(media_urls)} photos for Compass listing")
        
        return PropertyModel.MLSInfo(
            mls_id=mls_id,
            list_price=str(list_price),
            description=description,
            specs=specs,
            media_urls=media_urls,
            status=status
        )
    
    def _extract_media_urls_old_approach(self, listing: dict) -> list[str]:
        """Primary approach: Use the old simple method that was working well."""
        try:
            logger.info("[COMPASS] Starting old approach media extraction...")
            photos_sub_path = jmespath.search('media', listing)
            logger.info(f"[COMPASS] Media sub-path found: {photos_sub_path is not None}, Type: {type(photos_sub_path)}, Length: {len(photos_sub_path) if isinstance(photos_sub_path, list) else 'N/A'}")
            
            media_urls = [jmespath.search('originalUrl', photo) for photo in photos_sub_path] \
                if photos_sub_path else []
            
            logger.info(f"[COMPASS] Raw media URLs extracted: {len(media_urls)}")
            
            # Filter out None values and validate URLs
            valid_urls = [url for url in media_urls if url and isinstance(url, str) and url.startswith('http')]
            
            logger.info(f"[COMPASS] Old approach found {len(valid_urls)} valid images")
            for i, url in enumerate(valid_urls):
                logger.debug(f"[COMPASS] Old approach image {i+1}: {url}")
            
            return valid_urls
            
        except Exception as e:
            logger.error(f"[COMPASS] Error in old approach media extraction: {str(e)}")
            return []

    def _extract_media_urls_compass_api(self, listing: dict) -> list[str]:
        """Enhanced approach: Extract high-quality images from Compass API structure."""
        media_urls = []
        
        try:
            # Method 1: Extract from media array with quality analysis
            photos_sub_path = jmespath.search('media', listing)
            if photos_sub_path and isinstance(photos_sub_path, list):
                for photo in photos_sub_path:
                    if isinstance(photo, dict):
                        # Try to get the highest quality URL available
                        url = self._extract_highest_quality_compass_url(photo)
                        if url:
                            media_urls.append(url)
            
            # Method 2: Look for alternative media structures
            alternative_media = jmespath.search('photos', listing) or jmespath.search('images', listing)
            if alternative_media and isinstance(alternative_media, list):
                for photo in alternative_media:
                    if isinstance(photo, dict):
                        url = self._extract_highest_quality_compass_url(photo)
                        if url:
                            media_urls.append(url)
            
            # Method 3: Look for gallery data
            gallery_data = jmespath.search('gallery', listing)
            if gallery_data and isinstance(gallery_data, list):
                for item in gallery_data:
                    if isinstance(item, dict):
                        url = self._extract_highest_quality_compass_url(item)
                        if url:
                            media_urls.append(url)
            
            # Method 4: Deep search in the entire listing object
            if len(media_urls) < 5:  # If we don't have enough images
                media_urls.extend(self._deep_search_compass_images(listing))
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in media_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            
            logger.debug(f"[COMPASS] Compass API approach found {len(unique_urls)} high-quality images")
            return unique_urls
            
        except Exception as e:
            logger.error(f"[COMPASS] Error extracting media URLs from Compass API: {str(e)}")
            return []

    def _deep_search_compass_images(self, data: dict) -> list[str]:
        """Deep search for image URLs in the entire Compass data structure."""
        image_urls = []
        
        def _recursive_search(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    
                    # Look for image-related keys
                    if any(img_key in key.lower() for img_key in ['image', 'photo', 'media', 'url', 'src']):
                        if isinstance(value, str) and value.startswith('http'):
                            if re.search(r'\.(jpg|jpeg|png|webp)', value, re.I):
                                if self._is_compass_high_quality_url(value):
                                    image_urls.append(value)
                                    logger.debug(f"[COMPASS] Found image URL in {current_path}: {value[:100]}...")
                    
                    # Recursively search nested objects
                    _recursive_search(value, current_path)
                    
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    current_path = f"{path}[{i}]"
                    _recursive_search(item, current_path)
        
        try:
            _recursive_search(data)
            logger.debug(f"[COMPASS] Deep search found {len(image_urls)} additional image URLs")
            return image_urls
        except Exception as e:
            logger.error(f"[COMPASS] Error in deep search: {str(e)}")
            return []

    def _extract_highest_quality_compass_url(self, photo_dict: dict) -> str:
        """Extract the highest quality URL from a Compass photo dictionary."""
        if not isinstance(photo_dict, dict):
            return None
        
        # Compass-specific quality fields in order of preference
        quality_fields = [
            'originalUrl',      # Usually the highest quality
            'fullUrl',          # Full resolution
            'largeUrl',         # Large version
            'highResUrl',       # High resolution
            'fullScreenUrl',    # Full screen version
            'url',              # Standard URL
            'src',              # Source URL
            'imageUrl',         # Image URL
        ]
        
        for field in quality_fields:
            url = jmespath.search(field, photo_dict)
            if url and isinstance(url, str) and url.startswith('http'):
                # Additional Compass-specific quality validation
                if self._is_compass_high_quality_url(url):
                    logger.debug(f"[COMPASS] Selected Compass high-quality URL from field '{field}': {url[:100]}...")
                    return url
        
        return None

    def _is_compass_high_quality_url(self, url: str) -> bool:
        """Validate if a Compass URL points to a high-quality image."""
        if not url or not url.startswith('http'):
            return False
        
        url_lower = url.lower()
        
        # Compass-specific high-quality indicators
        compass_quality_indicators = [
            'original', 'full', 'large', 'high', 'hq', 'hd', 'fullscreen',
            '1920', '2048', '2560', '3840',  # Common high-res dimensions
            'originalUrl', 'fullUrl', 'largeUrl', 'highResUrl',
            # Compass-specific patterns
            'compass.com', 'images.compass.com', 'cdn.compass.com'
        ]
        
        # Check for quality indicators
        for indicator in compass_quality_indicators:
            if indicator in url_lower:
                return True
        
        # Check for size parameters in URL
        size_patterns = [
            r'w=\d+', r'width=\d+', r'h=\d+', r'height=\d+',
            r'size=\d+', r'dimensions=\d+'
        ]
        
        for pattern in size_patterns:
            if re.search(pattern, url_lower):
                # Extract size and check if it's large enough
                size_match = re.search(r'(\d+)', url_lower)
                if size_match:
                    size = int(size_match.group(1))
                    if size >= 800:  # Consider 800px+ as high quality
                        return True
        
        # If no quality indicators found, still accept if it's a direct image URL
        # but log for monitoring
        if any(ext in url_lower for ext in ['.jpg', '.jpeg', '.png', '.webp']):
            logger.debug(f"[COMPASS] Compass URL without quality indicators, accepting: {url[:100]}...")
            return True
        
        return False

    def _extract_from_next_data(self, soup: BeautifulSoup) -> PropertyModel.MLSInfo:
        """Extract data from __NEXT_DATA__ script tag (Compass Next.js approach)."""
        try:
            script_tag = soup.find("script", id="__NEXT_DATA__")
            if not script_tag:
                logger.debug("[COMPASS] No __NEXT_DATA__ script tag found")
                return None
            
            logger.info("[COMPASS] Found __NEXT_DATA__ script tag, parsing JSON data...")
            
            # Parse the JSON data
            data = json.loads(script_tag.string)
            logger.info(f"[COMPASS] Successfully parsed __NEXT_DATA__ JSON (size: {len(str(data))} chars)")
            
            # Navigate to the listing data
            listing = jmespath.search('props.pageProps.listing', data)
            if not listing:
                logger.warning("[COMPASS] No listing data found in __NEXT_DATA__ at props.pageProps.listing")
                # Try alternative paths
                listing = jmespath.search('props.listingRelation.listing', data)
                if listing:
                    logger.info("[COMPASS] Found listing data at alternative path: props.listingRelation.listing")
                else:
                    logger.warning("[COMPASS] No listing data found at alternative paths")
                    return None
            
            logger.info(f"[COMPASS] Found listing data with keys: {list(listing.keys()) if isinstance(listing, dict) else 'Not a dict'}")
            
            return self._extract_listing_info_from_next_data(listing)
            
        except Exception as e:
            logger.error(f"[COMPASS] Failed to extract from __NEXT_DATA__: {str(e)}")
            return None

    def _extract_listing_info_from_next_data(self, listing: dict) -> PropertyModel.MLSInfo:
        """Extract listing information from Next.js data structure."""
        try:
            logger.info("[COMPASS] Starting extraction from Next.js listing data...")
            
            # Extract basic listing info
            mls_id = jmespath.search('externalId', listing)
            list_price = jmespath.search('price.lastKnown', listing)
            description = jmespath.search('description', listing)
            
            # Extract status from various possible locations
            status = (jmespath.search('status', listing) or 
                     jmespath.search('listingStatus', listing) or
                     jmespath.search('mlsStatus', listing) or
                     jmespath.search('state', listing) or
                     jmespath.search('detailedInfo.keyDetails[?key=="Status"].value | [0]', listing) or
                     jmespath.search('detailedInfo.keyDetails[?key=="Listing Status"].value | [0]', listing))
            
            # Default to "Active" if no status found and property has price
            if not status and list_price:
                status = "Active"
            
            logger.info(f"[COMPASS] Basic info - MLS ID: {mls_id}, Price: {list_price}, Description length: {len(description) if description else 0}")
            
            # Extract high-quality images from photoGallery
            media_urls = self._extract_images_from_next_data(listing)
            
            # Extract specs
            specs = {}
            specs['property_type'] = jmespath.search("detailedInfo.keyDetails[?key=='Compass Type'].value | [0]", listing)
            specs['beds'] = jmespath.search('size.bedrooms', listing)
            specs['bath'] = jmespath.search('size.bathrooms', listing)
            specs['living_size'] = jmespath.search('size.squareFeet', listing)
            specs['lot_size'] = jmespath.search('size.lotSizeInSquareFeet', listing)
            
            logger.info(f"[COMPASS] Specs - Property Type: {specs['property_type']}, Beds: {specs['beds']}, Bath: {specs['bath']}, Living Size: {specs['living_size']}, Lot Size: {specs['lot_size']}")
            logger.info(f"[COMPASS] Extracted {len(media_urls)} high-quality photos from __NEXT_DATA__")
            
            return PropertyModel.MLSInfo(
                mls_id=mls_id,
                list_price=str(list_price) if list_price else None,
                description=description,
                specs=specs,
                media_urls=media_urls,
                status=status
            )
            
        except Exception as e:
            logger.error(f"[COMPASS] Error extracting listing info from Next.js data: {str(e)}")
            return None

    def _extract_images_from_next_data(self, listing: dict) -> list[str]:
        """Extract high-quality images from Next.js data structure."""
        media_urls = []
        
        try:
            logger.info("[COMPASS] Starting image extraction from Next.js data...")
            
            # Method 1: Extract from photoGallery (primary source)
            photo_gallery = jmespath.search('media.photoGallery', listing)
            logger.info(f"[COMPASS] Photo gallery found: {photo_gallery is not None}, Type: {type(photo_gallery)}, Length: {len(photo_gallery) if isinstance(photo_gallery, list) else 'N/A'}")
            
            if photo_gallery and isinstance(photo_gallery, list):
                logger.info(f"[COMPASS] Processing {len(photo_gallery)} items in photoGallery...")
                for i, item in enumerate(photo_gallery):
                    logger.debug(f"[COMPASS] Processing photoGallery item {i}: {list(item.keys()) if isinstance(item, dict) else type(item)}")
                    if isinstance(item, dict):
                        # Look for high-quality URL fields
                        url = self._extract_highest_quality_next_data_url(item)
                        if url:
                            media_urls.append(url)
                            logger.info(f"[COMPASS] Added high-quality URL from photoGallery[{i}]: {url[:100]}...")
                        else:
                            logger.debug(f"[COMPASS] No high-quality URL found in photoGallery[{i}]")
            
            # Method 2: Extract from media array (fallback)
            if not media_urls:
                logger.info("[COMPASS] No images from photoGallery, trying media array...")
                media_array = jmespath.search('media', listing)
                logger.info(f"[COMPASS] Media array found: {media_array is not None}, Type: {type(media_array)}, Length: {len(media_array) if isinstance(media_array, list) else 'N/A'}")
                
                if media_array and isinstance(media_array, list):
                    logger.info(f"[COMPASS] Processing {len(media_array)} items in media array...")
                    for i, item in enumerate(media_array):
                        logger.debug(f"[COMPASS] Processing media item {i}: {list(item.keys()) if isinstance(item, dict) else type(item)}")
                        if isinstance(item, dict):
                            url = self._extract_highest_quality_next_data_url(item)
                            if url:
                                media_urls.append(url)
                                logger.info(f"[COMPASS] Added high-quality URL from media[{i}]: {url[:100]}...")
                            else:
                                logger.debug(f"[COMPASS] No high-quality URL found in media[{i}]")
            
            # Method 3: Deep search in media structure
            if not media_urls:
                logger.info("[COMPASS] No images from media arrays, trying deep search...")
                media_urls = self._deep_search_next_data_images(listing)
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in media_urls:
                if url not in seen:
                    seen.add(url)
                    unique_urls.append(url)
            
            logger.info(f"[COMPASS] Next.js data approach found {len(unique_urls)} unique high-quality images")
            for i, url in enumerate(unique_urls):
                logger.debug(f"[COMPASS] Image {i+1}: {url}")
            
            return unique_urls
            
        except Exception as e:
            logger.error(f"[COMPASS] Error extracting images from Next.js data: {str(e)}")
            return []

    def _extract_highest_quality_next_data_url(self, item: dict) -> str:
        """Extract the highest quality URL from Next.js data item."""
        if not isinstance(item, dict):
            logger.debug(f"[COMPASS] Item is not a dict: {type(item)}")
            return None
        
        logger.debug(f"[COMPASS] Processing item with keys: {list(item.keys())}")
        
        # Next.js data quality fields in order of preference
        quality_fields = [
            'url',              # Usually the highest quality in Next.js data
            'originalUrl',      # Original URL
            'fullUrl',          # Full resolution
            'largeUrl',         # Large version
            'highResUrl',       # High resolution
            'fullScreenUrl',    # Full screen version
            'src',              # Source URL
            'imageUrl',         # Image URL
        ]
        
        for field in quality_fields:
            url = jmespath.search(field, item)
            if url and isinstance(url, str) and url.startswith('http'):
                logger.debug(f"[COMPASS] Found URL in field '{field}': {url[:100]}...")
                # Additional quality validation
                if self._is_compass_high_quality_url(url):
                    logger.info(f"[COMPASS] Selected Next.js high-quality URL from field '{field}': {url[:100]}...")
                    return url
                else:
                    logger.debug(f"[COMPASS] URL from field '{field}' failed quality validation")
            else:
                logger.debug(f"[COMPASS] No valid URL found in field '{field}'")
        
        logger.debug("[COMPASS] No high-quality URL found in any field")
        return None

    def _deep_search_next_data_images(self, data: dict) -> list[str]:
        """Deep search for image URLs in Next.js data structure."""
        image_urls = []
        
        def _recursive_search(obj, path=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    current_path = f"{path}.{key}" if path else key
                    
                    # Look for image-related keys in Next.js data
                    if any(img_key in key.lower() for img_key in ['image', 'photo', 'media', 'url', 'src', 'gallery']):
                        if isinstance(value, str) and value.startswith('http'):
                            if re.search(r'\.(jpg|jpeg|png|webp)', value, re.I):
                                if self._is_compass_high_quality_url(value):
                                    image_urls.append(value)
                                    logger.debug(f"[COMPASS] Found Next.js image URL in {current_path}: {value[:100]}...")
                    
                    # Recursively search nested objects
                    _recursive_search(value, current_path)
                    
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    current_path = f"{path}[{i}]"
                    _recursive_search(item, current_path)
        
        try:
            _recursive_search(data)
            logger.debug(f"[COMPASS] Next.js deep search found {len(image_urls)} additional image URLs")
            return image_urls
        except Exception as e:
            logger.error(f"[COMPASS] Error in Next.js deep search: {str(e)}")
            return []

    def _find_exact_address_match(self, input_address: str, items: list) -> dict | None:
        """Find an exact match for the input address in the autocomplete suggestions."""
        input_address_normalized = self._normalize_address_for_matching(input_address)
        
        for item in items:
            item_address_normalized = self._normalize_address_for_matching(item['text'])
            if input_address_normalized == item_address_normalized:
                logger.debug(f"[COMPASS] Exact address match found: '{item['text']}' matches '{input_address}'")
                return item
        
        logger.debug(f"[COMPASS] No exact address match found for '{input_address}'")
        logger.debug(f"[COMPASS] Available addresses: {[item['text'] for item in items]}")
        return None
    
    def _normalize_address_for_matching(self, address: str) -> str:
        """Normalize address for exact matching comparison."""
        if not address:
            return ""
        
        # Convert to lowercase and strip whitespace
        normalized = address.lower().strip()
        
        # Remove common punctuation that might cause mismatches
        normalized = re.sub(r'[^\w\s]', '', normalized)
        
        # Normalize whitespace (multiple spaces to single space)
        normalized = re.sub(r'\s+', ' ', normalized)
        
        return normalized

    def _check_playwright_installation(self):
        """Check if Playwright is properly installed and install browsers if needed."""
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                # Try to launch browser to check if browsers are installed
                browser = p.chromium.launch(headless=True)
                browser.close()
            logger.info("Playwright browsers are properly installed")
            return True
        except Exception as e:
            logger.warning(f"Playwright browsers not installed: {str(e)}")
            logger.info("Installing Playwright browsers...")
            try:
                import subprocess
                subprocess.run(["playwright", "install", "chromium"], check=True)
                logger.info("Playwright browsers installed successfully")
                return True
            except Exception as install_error:
                logger.error(f"Failed to install Playwright browsers: {str(install_error)}")
                return False

    def _extract_images_with_playwright(self, property_url: str) -> list[str]:
        """Extract high-quality images using Playwright to walk through the carousel."""
        image_urls = set()
        
        try:
            # Import Playwright here to avoid dependency issues if not installed
            from playwright.sync_api import sync_playwright
            
            logger.info(f"[COMPASS] A Starting Playwright image extraction for: {property_url}")
            
            # Check if Playwright is properly installed
            if not self._check_playwright_installation():
                logger.error("[COMPASS] Playwright not properly installed, skipping image extraction")
                return []
            
            logger.info(f"[COMPASS] B Starting Playwright image extraction for: {property_url}")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Set user agent to avoid detection
                page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                })
                
                page.goto(property_url, timeout=60000)
                logger.info("[COMPASS] Page loaded successfully")
                
                # Wait for carousel to load
                carousel_found = False
                try:
                    page.wait_for_selector("button[data-testid='MediaCarousel-nextButton']", timeout=15000)
                    logger.info("[COMPASS] Carousel next button found")
                    carousel_found = True
                except Exception as e:
                    logger.warning(f"Carousel next button not found: {str(e)}")
                    # Try alternative selectors
                    try:
                        page.wait_for_selector("[data-testid*='next']", timeout=5000)
                        logger.info("[COMPASS] Alternative next button found")
                        carousel_found = True
                    except:
                        logger.warning("[COMPASS] No next button found, will try to extract static images")
                
                # Loop through the carousel if found
                if carousel_found:
                    for slide_index in range(50):  # Arbitrary max slides
                        logger.debug(f"[COMPASS] Processing slide {slide_index + 1}")
                        
                        # Collect visible images
                        images = page.query_selector_all("img")
                        logger.debug(f"[COMPASS] Found {len(images)} images on current slide")
                        
                        for img in images:
                            try:
                                # Try to get srcset first (highest quality)
                                srcset = img.get_attribute("srcset")
                                if srcset:
                                    # Extract highest resolution from srcset
                                    candidates = [s.strip().split(" ")[0] for s in srcset.split(",")]
                                    if candidates:
                                        highest_res = candidates[-1]  # Last one is usually highest resolution
                                        image_urls.add(highest_res)
                                        logger.debug(f"Added high-res image from srcset: {highest_res[:100]}...")
                                
                                # Also try regular src attribute
                                src = img.get_attribute("src")
                                if src and src.startswith('http'):
                                    # Check if it's a high-quality image
                                    if self._is_compass_high_quality_url(src):
                                        image_urls.add(src)
                                        logger.debug(f"Added high-quality image from src: {src[:100]}...")
                                        
                            except Exception as e:
                                logger.debug(f"Error processing image: {str(e)}")
                        
                        # Try clicking next
                        try:
                            next_button = page.query_selector("button[data-testid='MediaCarousel-nextButton']")
                            if not next_button:
                                # Try alternative selectors
                                next_button = page.query_selector("[data-testid*='next']")
                            
                            if next_button and next_button.is_enabled():
                                next_button.click()
                                time.sleep(0.5)  # Wait for images to load
                                logger.debug(f"Clicked next button for slide {slide_index + 1}")
                            else:
                                logger.info("[COMPASS] Next button not available or disabled, stopping carousel navigation")
                                break
                        except Exception as e:
                            logger.debug(f"Error clicking next button: {str(e)}")
                            break
                else:
                    # Fallback: extract all images from the page without carousel navigation
                    logger.info("Extracting static images from page (no carousel navigation)")
                    images = page.query_selector_all("img")
                    logger.debug(f"Found {len(images)} static images")
                    
                    for img in images:
                        try:
                            # Try to get srcset first (highest quality)
                            srcset = img.get_attribute("srcset")
                            if srcset:
                                # Extract highest resolution from srcset
                                candidates = [s.strip().split(" ")[0] for s in srcset.split(",")]
                                if candidates:
                                    highest_res = candidates[-1]  # Last one is usually highest resolution
                                    image_urls.add(highest_res)
                                    logger.debug(f"Added high-res image from srcset: {highest_res[:100]}...")
                            
                            # Also try regular src attribute
                            src = img.get_attribute("src")
                            if src and src.startswith('http'):
                                # Check if it's a high-quality image
                                if self._is_compass_high_quality_url(src):
                                    image_urls.add(src)
                                    logger.debug(f"Added high-quality image from src: {src[:100]}...")
                                    
                        except Exception as e:
                            logger.debug(f"Error processing static image: {str(e)}")
                
                browser.close()
            
            result = list(image_urls)
            logger.info(f"Playwright extraction completed. Found {len(result)} unique high-quality images")
            return result
            
        except ImportError:
            logger.error("Playwright not installed. Install with: pip install playwright && playwright install")
            return []
        except Exception as e:
            logger.error(f"Error in Playwright image extraction: {str(e)}")
            return []

# For testing purposes only
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Compass Scraper')

    parser.add_argument('-a', '--address', required=True, type=str, help='Property address to search for')
    
    args = parser.parse_args()
    address = Address(args.address)
    
    try:
        engine = Compass()
        mls_info = engine.get_property_info(address)
        # compass = 'playground/output/compass.json'
        # with open(compass, 'w', encoding="utf-8") as file:
        #     json.dump(mls_info, file, indent=2)
        
        print(mls_info)
                
    except Exception as e:
        logger.exception(e)
        
        
if __name__ == '__main__':
    main()    
    

