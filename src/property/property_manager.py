import os
from pathlib import Path
import tempfile
import wget
import argparse
from urllib.parse import urlparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor, as_completed

from logger import logger
from config.config import settings
from property.address import Address
from property.scraper_engines import ScraperEngineManager, get_tenant_engine_summary
from property.scrapers.jenna_cooper_la import JennaCooperLA  # Needed for search_by_title method
from property.property_model import PropertyModel
from property.status_validator import status_validator
from ai.script_manager import ScriptManager
from gcp.db import db_client
from gcp.storage import StorageManager
from gcp.storage_model import CloudPath


class PropertyManager():
    """
    PropertyManager handles property data extraction using multiple scraping engines.
    
    Engine configuration is now managed by ScraperEngineManager in scraper_engines.py.
    This class focuses on the core property management logic while delegating
    engine selection and configuration to the dedicated engine manager.
    """
    
    def __init__(self, address:str, tenant_id:str="editora", address_input_type:Address.AddressInputType=Address.AddressInputType.AutoComplete, title:str=None):
        self.tenant_id = tenant_id
        self.title = title
        logger.info(f"[PROPERTY_MANAGER] Initializing with tenant_id: '{tenant_id}' for address: '{address}'")
        if title:
            logger.info(f"[PROPERTY_MANAGER] Title provided: '{title}'")
        
        # Get engines from ScraperEngineManager
        self.engines = ScraperEngineManager.get_engines_for_tenant(tenant_id)
        logger.info(f"[PROPERTY_MANAGER] Selected engines for tenant '{tenant_id}': {[engine.__class__.__name__ for engine in self.engines]}")
        
        self.address = Address(address, address_input_type, tenant_id)
        self.property = None
    
    def get_engine_summary(self) -> dict:
        """Get a summary of the current engine configuration for debugging"""
        return get_tenant_engine_summary(self.tenant_id)
        
    def fetch_property(self)->PropertyModel:
        logger.info(f"[PROPERTY_MANAGER] Starting fetch_property for address: '{self.address}'")
        logger.info(f"[PROPERTY_MANAGER] Address details:")
        logger.info(f"[PROPERTY_MANAGER]   - Input address: '{self.address.input_address}'")
        logger.info(f"[PROPERTY_MANAGER]   - Formatted address: '{self.address.formatted_address}'")
        logger.info(f"[PROPERTY_MANAGER]   - Short formatted address: '{self.address.short_formatted_address}'")
        logger.info(f"[PROPERTY_MANAGER]   - Place ID: '{self.address.place_id}'")
        logger.info(f"[PROPERTY_MANAGER]   - Address input type: {self.address.address_input_type.name}")
        
        def _freshness_check()->tuple[bool, PropertyModel]:
            # Determine the property ID for caching
            if (self.address.address_input_type == Address.AddressInputType.PropertyTitle and 
                self.tenant_id == "jenna_cooper_la"):
                # For title searches, generate ID from title
                search_title = self.title if self.title else self.address.input_address
                property_id = f"title_{search_title.lower().replace(' ', '_')}"
                logger.info(f"[PROPERTY_MANAGER] PropertyTitle search detected - using property_id: '{property_id}' for caching")
            else:
                # Regular address-based search
                property_id = self.address.place_id
                logger.info(f"[PROPERTY_MANAGER] Regular address search - using place_id: '{property_id}' for caching")
            
            doc_ref = db_client.collection(settings.GCP.Firestore.PROPERTIES_COLLECTION_NAME).document(property_id)
            doc = doc_ref.get()
            if doc.exists:
                existing_property = PropertyModel.model_validate(doc.to_dict())
                timezone = existing_property.extraction_time.tzinfo
                if datetime.now(timezone) - existing_property.extraction_time < timedelta(hours=settings.Property.RESCRAPE_AFTER):
                    logger.warning(f"Property '{self.address}', ID '{property_id}' extracted within the last {settings.Property.RESCRAPE_AFTER} hour(s)")
                    
                    # Log the complete folder structure for cached property
                    cached_folder_path = f"{property_id}/{settings.Property.IMAGES_DIR}"
                    cached_cloud_path = f"gs://{settings.GCP.Storage.PROPERTIES_BUCKET}/{cached_folder_path}"
                    logger.info(f"Cached property found - Property ID: '{property_id}'")
                    logger.info(f"Cached property folder structure: '{cached_cloud_path}'")
                    logger.info(f"Property metadata stored in Firestore collection: '{settings.GCP.Firestore.PROPERTIES_COLLECTION_NAME}' with document ID: '{property_id}'")
                    logger.info(f"[PROPERTY_MANAGER] Cached property script: {existing_property.script[:100] if existing_property.script else 'None'}...")
                    
                    return True, existing_property
                
            return False, None
        
        fresh, self.property = _freshness_check()
        if fresh:
            # Data came from cache, source is the extraction engine that was used originally
            source = f"cache_{self.property.extraction_engine.lower()}"
            return self.property, source
        
        # Check if this is a PropertyTitle search for Jenna Cooper LA
        if (self.address.address_input_type == Address.AddressInputType.PropertyTitle and 
            self.tenant_id == "jenna_cooper_la"):
            logger.info(f"[PROPERTY_MANAGER] PropertyTitle search detected for Jenna Cooper LA")
            search_title = self.title if self.title else self.address.input_address
            logger.info(f"[PROPERTY_MANAGER] Using title search with title: '{search_title}'")
            return self.search_by_title(search_title)
                
        # Cycle through all engines as needed
        mls_info = None
        extraction_engine = None
        
        for engine in self.engines:
            engine_name = engine.__class__.__name__
            logger.info(f"[SCRAPER] Trying engine: {engine_name} for address '{self.address}'")
            
            try:
                # For Jenna Cooper LA, pass the title parameter if available
                if engine_name == "JennaCooperLA" and self.title:
                    logger.info(f"[SCRAPER] Passing title '{self.title}' to JennaCooperLA engine")
                    mls_info = engine.get_property_info(address_obj=self.address, title=self.title)
                else:
                    mls_info = engine.get_property_info(address_obj=self.address)
                    
                if mls_info:
                    # Check if property status is inactive
                    if hasattr(mls_info, 'status') and mls_info.status:
                        if status_validator.is_property_inactive(mls_info.status, engine_name):
                            logger.warning(f"[SCRAPER] {engine_name} found property but status '{mls_info.status}' is inactive")
                            raise ValueError("This listing isn't available. Please upload your own images or enter a different address to continue.")
                    
                    # Check if we have images
                    image_count = len(getattr(mls_info, 'media_urls', []))
                    logger.info(f"[SCRAPER] {engine_name} found property with {image_count} images")
                    
                    if image_count > 0:
                        extraction_engine = engine_name
                        logger.success(f"[SCRAPER] SUCCESS: {engine_name} extracted MLS info for '{self.address}'. MLS ID: {getattr(mls_info, 'mls_id', None)}, Images: {image_count}")
                        logger.info(f"[SCRAPER] MLS Info: {mls_info}")
                        break
                    else:
                        logger.warning(f"[SCRAPER] {engine_name} found property but has no images, trying next engine")
                        # Continue to next engine to find one with images
                        continue
                else:
                    logger.warning(f"[SCRAPER] {engine_name} returned no data for address '{self.address}'")
            except Exception as e:
                logger.error(f"[SCRAPER] {engine_name} failed to scrape address '{self.address}': {str(e)}")
                continue
                
        if not mls_info:
            logger.error(f"Failed to scrape address '{self.address}' from all {len(self.engines)} engines")
            return None, None
        
        # Determine the property ID consistently with freshness check
        if (self.address.address_input_type == Address.AddressInputType.PropertyTitle and 
            self.tenant_id == "jenna_cooper_la"):
            # For title searches, generate ID from title
            search_title = self.title if self.title else self.address.input_address
            property_id = f"title_{search_title.lower().replace(' ', '_')}"
            property_address = search_title  # Use title as address
            logger.info(f"[PROPERTY_MANAGER] Creating PropertyModel with title-based ID: '{property_id}'")
        else:
            # Regular address-based search
            property_id = self.address.place_id
            property_address = self.address.short_formatted_address
            logger.info(f"[PROPERTY_MANAGER] Creating PropertyModel with place_id: '{property_id}'")
        
        # Determine the property ID consistently with freshness check
        if (self.address.address_input_type == Address.AddressInputType.PropertyTitle and 
            self.tenant_id == "jenna_cooper_la"):
            # For title searches, generate ID from title
            search_title = self.title if self.title else self.address.input_address
            property_id = f"title_{search_title.lower().replace(' ', '_')}"
            property_address = search_title  # Use title as address
            logger.info(f"[PROPERTY_MANAGER] Creating PropertyModel with title-based ID: '{property_id}'")
        else:
            # Regular address-based search
            property_id = self.address.place_id
            property_address = self.address.short_formatted_address
            logger.info(f"[PROPERTY_MANAGER] Creating PropertyModel with place_id: '{property_id}'")
        
        self.property = PropertyModel(
                id=property_id,
                address=property_address,
                extraction_engine=extraction_engine,
                extraction_time=datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)),
                mls_info=mls_info)
        
        script_mgr = ScriptManager()
        logger.info(f"[PROPERTY_MANAGER] Generating script from description: {mls_info.description[:100] if mls_info.description else 'None'}...")
        self.property.script = script_mgr.generate_script(description=mls_info.description)
        logger.info(f"[PROPERTY_MANAGER] Generated script: {self.property.script[:100] if self.property.script else 'None'}...")
        
        try:    
            self.save_property(mls_info.media_urls)
            logger.success(f"Successfully processed and saved property '{self.address}'")
            # Data came from fresh extraction, source is the extraction engine
            source = extraction_engine.lower()
            return self.property, source
        except Exception as e:
            logger.exception(f"Failed to save property '{self.address}': {str(e)}")
            return None, None
                
    def save_property(self, media_urls:list[str]):
        if not media_urls:
            logger.warning(f"No images were extracted for property {self.address}")
            raise ValueError(f'No images were extracted for property {self.address}')
        
        # Use property ID for Firestore document and cloud storage path
        property_id = self.property.id
        logger.info(f"[PROPERTY_MANAGER] Using property_id '{property_id}' for saving property")
        
        doc_ref = db_client.collection(settings.GCP.Firestore.PROPERTIES_COLLECTION_NAME).document(property_id)
        
        dir_path = f"{property_id}/{settings.Property.IMAGES_DIR}"
        cloud_path = CloudPath(bucket_id=settings.GCP.Storage.PROPERTIES_BUCKET, path=Path(dir_path))
        
        self.save_images(urls=media_urls, path=cloud_path)

        self.property.media_storage_path = f"gs://{cloud_path.bucket_id}/{cloud_path.path}"                
        doc_ref.set(self.property.model_dump())
        logger.success(f"Saved Property in Firestore. Address : {self.property.address}, ID : {self.property.id}")
        
        
    def save_images(self, urls: list[str], path: CloudPath):
        logger.info(f"[PROPERTY_MANAGER] Starting download of {len(urls)} images")
        
        # Filter out problematic URLs
        valid_urls = []
        for url in urls:
            # Check if this is a srcset string and extract highest resolution
            if ',' in url and 'w' in url:
                logger.debug(f"[PROPERTY_MANAGER] Detected srcset string, extracting highest resolution: {url[:100]}...")
                highest_res_url = self._extract_highest_resolution_from_srcset(url)
                if highest_res_url:
                    url = highest_res_url
                    logger.debug(f"[PROPERTY_MANAGER] Using highest resolution URL: {url}")
                else:
                    logger.warning(f"[PROPERTY_MANAGER] Failed to extract URL from srcset: {url}")
                    continue
            
            if self._is_valid_image_url(url):
                valid_urls.append(url)
            else:
                logger.warning(f"[PROPERTY_MANAGER] Skipping invalid URL: {url}")
        
        logger.info(f"[PROPERTY_MANAGER] Filtered to {len(valid_urls)} valid URLs from {len(urls)} total")
        
        if not valid_urls:
            logger.error(f"[PROPERTY_MANAGER] No valid image URLs found for property '{str(self.address)}'")
            raise ValueError(f"No valid image URLs found for property '{str(self.address)}'")
        
        with tempfile.TemporaryDirectory() as tempdir:
            futures = []
            # Limit concurrent downloads to avoid timeouts
            max_workers = min(5, len(urls))  # Max 5 concurrent downloads
            logger.info(f"[PROPERTY_MANAGER] Using {max_workers} concurrent download workers")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all download tasks
                for idx, url in enumerate(valid_urls, start=1):
                    ext = self._get_file_extension(url=url)
                    filename = f"image{idx}{ext}"
                    full_local_path = Path(tempdir, filename)
                    logger.debug(f"[PROPERTY_MANAGER] Submitting download task {idx}/{len(valid_urls)}: {url}")
                    futures.append(
                        executor.submit(self._download_image_with_timeout, url=url, local_path=str(full_local_path))
                    )

                # Wait for all downloads to complete
                completed_downloads = 0
                failed_downloads = 0
                for i, future in enumerate(as_completed(futures), 1):
                    try:
                        # This will re-raise any exceptions that occurred during downloading
                        future.result()
                        completed_downloads += 1
                        logger.debug(f"[PROPERTY_MANAGER] Download {i}/{len(valid_urls)} completed successfully")
                    except Exception as e:
                        failed_downloads += 1
                        logger.error(f"[PROPERTY_MANAGER] Download {i}/{len(valid_urls)} failed: {str(e)}")

            logger.info(f"[PROPERTY_MANAGER] Download summary: {completed_downloads} successful, {failed_downloads} failed")
            
            # Check if we have at least some successful downloads
            if completed_downloads == 0:
                logger.error(f"[PROPERTY_MANAGER] No images downloaded successfully for property '{str(self.address)}'")
                raise ValueError(f"No images downloaded successfully for property '{str(self.address)}'")
            
            # Once all downloads are complete, save the blobs
            StorageManager.save_blobs(source_dir=Path(tempdir), cloud_path=path)
            logger.success(f"Successfully uploaded {completed_downloads} images to cloud storage for property '{str(self.address)}'")
    
    def _download_image_with_timeout(self, url: str, local_path: str):
        """Download image with timeout handling using Python requests"""
        try:
            import requests
            from pathlib import Path
            
            # Set timeout to 30 seconds
            timeout = 30
            
            # Download with requests
            response = requests.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Save to file
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        except requests.exceptions.Timeout:
            logger.warning(f"Download timeout for URL: {url}")
            raise Exception(f"Download timeout for URL: {url}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Download failed for URL {url}: {str(e)}")
            raise Exception(f"Download failed for URL {url}: {str(e)}")
        except Exception as e:
            logger.error(f"Download failed for URL {url}: {str(e)}")
            raise
    
    def _is_valid_image_url(self, url: str) -> bool:
        """Validate if a URL is suitable for image download"""
        if not url:
            logger.debug(f"[PROPERTY_MANAGER] URL validation failed: empty URL")
            return False
        
        # Check for control characters or spaces
        if ' ' in url or '\n' in url or '\r' in url or '\t' in url:
            logger.debug(f"[PROPERTY_MANAGER] URL validation failed: contains control characters: {url}")
            return False
        
        # Check if it's a valid HTTP URL
        if not url.startswith('http'):
            logger.debug(f"[PROPERTY_MANAGER] URL validation failed: not HTTP URL: {url}")
            return False
        
        # For Shopify CDN URLs, be very permissive
        if 'cdn.shopify.com' in url or 'jennacooperla.com/cdn/shop' in url:
            # Accept any Shopify CDN URL that contains /files/ in the path
            if '/files/' in url:
                logger.debug(f"[PROPERTY_MANAGER] URL validation passed: Shopify CDN with /files/: {url}")
                return True
            # Also accept URLs with image patterns
            url_lower = url.lower()
            if any(pattern in url_lower for pattern in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', 'image', 'photo', 'img']):
                logger.debug(f"[PROPERTY_MANAGER] URL validation passed: Shopify CDN with image pattern: {url}")
                return True
        
        # For Corcoran CDN URLs, be very permissive
        if 'corcoranlabs.com' in url or 'media-cloud.corcoranlabs.com' in url:
            # Accept any Corcoran CDN URL that contains ListingFullAPI or media-cloud in the path
            if '/ListingFullAPI/' in url or '/media-cloud/' in url:
                logger.debug(f"[PROPERTY_MANAGER] URL validation passed: Corcoran CDN with ListingFullAPI/media-cloud: {url}")
                return True
            # Also accept URLs with image patterns
            url_lower = url.lower()
            if any(pattern in url_lower for pattern in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', 'image', 'photo', 'img']):
                logger.debug(f"[PROPERTY_MANAGER] URL validation passed: Corcoran CDN with image pattern: {url}")
                return True
        
        # For other URLs, check for common image extensions
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff']
        url_lower = url.lower()
        if not any(ext in url_lower for ext in image_extensions):
            logger.debug(f"[PROPERTY_MANAGER] URL validation failed: no image extension found: {url}")
            return False
        
        logger.debug(f"[PROPERTY_MANAGER] URL validation passed: has image extension: {url}")
        return True
    
    def _extract_highest_resolution_from_srcset(self, srcset: str) -> str:
        """Extract the highest resolution URL from a srcset string"""
        if not srcset or ',' not in srcset:
            return None
            
        try:
            # Parse srcset format: "url1 width1, url2 width2, ..."
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
                logger.debug(f"[PROPERTY_MANAGER] Extracted highest resolution URL from srcset: {highest_res_url}")
                return highest_res_url
                
        except Exception as e:
            logger.warning(f"[PROPERTY_MANAGER] Failed to parse srcset: {str(e)}")
            
        return None
            

    def _get_file_extension(self, url)->str:
        """Extracts the file extension from a URL."""
        parsed_url = urlparse(url)
        path = parsed_url.path
        if not path:
            # For Shopify CDN URLs without explicit extensions, default to .jpg
            if 'cdn.shopify.com' in url or 'jennacooperla.com/cdn/shop' in url:
                return '.jpg'
            # For Corcoran CDN URLs without explicit extensions, default to .jpg
            if 'corcoranlabs.com' in url or 'media-cloud.corcoranlabs.com' in url:
                return '.jpg'
            raise FileNotFoundError(f"File extension cannot be extracted from URL {url}")
        _, ext = os.path.splitext(path)
        if not ext:
            # For Shopify CDN URLs without explicit extensions, default to .jpg
            if 'cdn.shopify.com' in url or 'jennacooperla.com/cdn/shop' in url:
                return '.jpg'
            # For Corcoran CDN URLs without explicit extensions, default to .jpg
            if 'corcoranlabs.com' in url or 'media-cloud.corcoranlabs.com' in url:
                return '.jpg'
            raise FileNotFoundError(f"File extension cannot be extracted from URL {url}")
        return ext
        
    def search_by_title(self, title: str) -> PropertyModel:
        """Search for property by title (for Jenna Cooper LA tenants)"""
        
        logger.info(f"[PROPERTY_MANAGER] Starting title search for: '{title}' with tenant_id: '{self.tenant_id}'")
        
        if self.tenant_id != "jenna_cooper_la":
            logger.error(f"[PROPERTY_MANAGER] Title search is only supported for jenna_cooper_la tenant, got: '{self.tenant_id}'")
            return None
        
        # Check if we have a Jenna Cooper LA engine
        jenna_cooper_engine = None
        for engine in self.engines:
            if engine.__class__.__name__ == "JennaCooperLA":
                jenna_cooper_engine = engine
                break
        
        if not jenna_cooper_engine:
            logger.error(f"[PROPERTY_MANAGER] No JennaCooperLA engine found for tenant: '{self.tenant_id}'")
            return None
        
        try:
            # Use the Jenna Cooper LA engine's title search method
            mls_info = jenna_cooper_engine.search_by_title(title)
            
            if not mls_info:
                logger.error(f"[PROPERTY_MANAGER] No property found for title: '{title}'")
                return None
            
            # Check if property status is inactive
            if hasattr(mls_info, 'status') and mls_info.status:
                if status_validator.is_property_inactive(mls_info.status, "JennaCooperLA"):
                    logger.warning(f"[PROPERTY_MANAGER] Property found for title '{title}' but status '{mls_info.status}' is inactive")
                    raise ValueError("This listing isn't available. Please upload your own images or enter a different address to continue.")
            
            # Create property model
            self.property = PropertyModel(
                id=f"title_{title.lower().replace(' ', '_')}",  # Generate ID from title
                address=title,  # Use title as address
                extraction_engine="JennaCooperLA",
                extraction_time=datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)),
                mls_info=mls_info
            )
            
            # Generate script
            script_mgr = ScriptManager()
            self.property.script = script_mgr.generate_script(description=mls_info.description)
            
            # Save property
            try:
                self.save_property(mls_info.media_urls)
                logger.success(f"[PROPERTY_MANAGER] Successfully processed and saved property for title: '{title}'")
                return self.property
            except Exception as e:
                logger.exception(f"[PROPERTY_MANAGER] Failed to save property for title '{title}': {str(e)}")
                return None
                
        except Exception as e:
            logger.exception(f"[PROPERTY_MANAGER] Exception during title search for '{title}': {str(e)}")
            return None
        
####

# For testing purposes only
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Property fetcher')

    parser.add_argument('-a', '--address', required=True, type=str, help='Property address to search for')
    parser.add_argument('-t', '--type', choices=['autocomplete', 'freeform'], default='autocomplete', 
                        help='Address input type: autocomplete (uses Google Places API) or freeform (uses usaddress)')
    
    args = parser.parse_args()
    
    try:
        # Convert string input type to enum
        input_type = (Address.AddressInputType.AutoComplete 
                     if args.type == 'autocomplete' 
                     else Address.AddressInputType.FreeForm)
        
        property_mgr = PropertyManager(address=args.address, address_input_type=input_type)
        result = property_mgr.fetch_property()
        
        if result:
            logger.success(f"Property fetch completed successfully for address: '{args.address}'")
        else:
            logger.error(f"Property fetch failed for address: '{args.address}'")
                
    except Exception as e:
        logger.exception(f"Property fetch failed with exception: {str(e)}")
        
        
if __name__ == '__main__':
    main()    
