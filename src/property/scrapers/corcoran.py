import requests
from bs4 import BeautifulSoup
import json
import jmespath
import inflection
import argparse
from rich import print
from functools import reduce

from logger import logger
from config.config import settings
from property.scrapers.scraper_base import ScraperBase
from property.property_model import PropertyModel
from property.address import Address

class Corcoran(ScraperBase):
    def __init__(self):
        pass
    
    def get_property_info(self, address_obj:Address)->PropertyModel.MLSInfo:
        
        logger.info(f"{self.__class__.__name__} - Fetching listing information for property address : {address_obj.input_address}")
        
        for address in address_obj.plausible_address_matches():
            
            logger.debug(f"Attempting to fetch listing from address variation - {address}")
            
            # search listings
            url = "https://backendapi.corcoranlabs.com/api/search/autocomplete/poc"
            payload = {
                "page": 1,
                "pageSize": 10,
                "mode": "buy",
                "keywordSearch": address,
            }
            
            headers = Corcoran.HEADERS.copy()
            headers.update({"Be-Api-Key": "667256B5BF6ABFF6C8BDC68E88226"})
            
            try:
                response = requests.post(url, headers=headers, json=payload)    
                response.raise_for_status()
                extra={
                        "url": url,
                        "status_code": response.status_code,
                        "response_body": response.text
                    }
                logger.debug(
                    f"HTTP request succeeded\n{extra}"
                )

                response_json = response.json()

                if not response_json.get("listings"):
                    logger.warning(f"Corcoran found no listings for address - {address}")
                    continue
                
                if not response_json["listings"].get("items"):
                    logger.warning(f"Corcoran found no listing items for address - {address}")
                    continue
                
                if len(response_json["listings"]["items"]) == 0:
                    logger.warning(f"Corcoran found empty listing items for address - {address}")
                    continue
                
                response_json = response_json["listings"]["items"][0]
            
                # Build property slug, filtering out None values
                property_slug_parts = [
                    response_json.get("address1"),
                    response_json.get("address2"),
                    response_json.get("borough"),
                    response_json.get("state"),
                    response_json.get("zipCode"),
                ]
                # Filter out None values and empty strings
                property_slug_parts = [part for part in property_slug_parts if part]
                property_slug = " ".join(property_slug_parts)
                property_slug = inflection.parameterize(property_slug)
                
                # Add defensive check for empty property slug
                if not property_slug.strip():
                    logger.warning(f"Could not generate property slug for listing ID {response_json['id']}")
                    continue

                url = f"https://www.corcoran.com/listing/for-sale/{property_slug}/{response_json['id']}/regionId/{response_json['regionId']}"
                logger.debug(f"Generated property slug: '{property_slug}' for listing ID {response_json['id']}")
                logger.debug(f"Constructed Corcoran URL: {url}")
                
                response = requests.get(url, headers=headers)
                soup = BeautifulSoup(response.content, 'html.parser')
                script_tag = soup.find('script', id='__NEXT_DATA__', type='application/json')
        
                # Check if the script tag was found
                if script_tag:
                    # Extract the JSON string from the script tag
                    json_str = script_tag.string
                    json_data = json.loads(json_str)
                    mls_info = self._extract_listing_info_json(json_data=json_data)
                    
                    # Validate that we have essential data
                    if mls_info and mls_info.media_urls and len(mls_info.media_urls) > 0:
                        logger.info(f"Corcoran successfully extracted property data for {address}")
                        return mls_info
                    else:
                        logger.warning(f"Corcoran found property but has no valid media URLs for {address}")
                        continue
                else:
                    logger.warning(f"Corcoran property page has no __NEXT_DATA__ script for {address}")
                    continue

            except requests.exceptions.HTTPError as he:
                extra={
                        "url": url,
                        "status_code": he.response.status_code,
                        "reason": he.response.reason,
                        "response_body": he.response.text
                    }
                logger.error(
                    f"HTTP request failed\n{extra}",
                )
                continue  # Try next address variation
            except ValueError as ve:
                logger.error(f"ValueError for address {address}: {ve}")
                continue  # Try next address variation
            except Exception as e:
                logger.exception(f"Unexpected error for address {address}: {e}")
                continue  # Try next address variation
            
        logger.warning(f"Corcoran failed to fetch listing for all address variations - {address_obj.formatted_address}")
        return None
            
    def _extract_listing_info_json(self, json_data:dict)->PropertyModel.MLSInfo:
        listing = jmespath.search('props.pageProps.listing', json_data) 
        
        mls_id = jmespath.search('leadListingId', listing)
        list_price = jmespath.search('price', listing)
        description = jmespath.search('description', listing)
        
        # Extract status from various possible locations
        status = (jmespath.search('status', listing) or 
                 jmespath.search('listingStatus', listing) or
                 jmespath.search('mlsStatus', listing) or
                 jmespath.search('marketingStatus', listing))
        
        # Default to "Active" if no status found and property has price
        if not status and list_price:
            status = "Active"
        photos_sub_path = jmespath.search('media', listing)
        media_urls = [jmespath.search('url', photo) for photo in photos_sub_path] \
            if photos_sub_path else []
        
        specs = {}
        specs['property_type'] = jmespath.search('propertyType', listing)
        specs['beds'] = jmespath.search('bedrooms', listing)
        specs['bath'] = jmespath.search('bathrooms', listing)
        specs['living_size'] = jmespath.search('squareFootage', listing)
        
        # Fix the TypeError by adding null check for acreage
        acreage = jmespath.search('acreage', listing)
        if acreage is not None:
            try:
                specs['lot_size'] = str(round(float(acreage) * 43560))  # Acres -> SqFt
            except (ValueError, TypeError):
                logger.warning(f"Invalid acreage value: {acreage}, setting lot_size to None")
                specs['lot_size'] = None
        else:
            specs['lot_size'] = None
        
        return PropertyModel.MLSInfo(
            mls_id=mls_id,
            list_price=str(list_price) if list_price else None,
            description=description,
            specs=specs,
            media_urls=media_urls,
            status=status
        )

# For testing purposes only
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Corcoran Scraper')

    parser.add_argument('-a', '--address', required=True, type=str, help='Property address to search for')
    
    args = parser.parse_args()
    address = Address(args.address)
    
    try:
        engine = Corcoran()
        mls_info = engine.get_property_info(address)
        # corcoran = 'playground/output/corcoran.json'
        # with open(corcoran, 'w', encoding="utf-8") as file:
        #     json.dump(mls_info, file, indent=2)
        
        print(mls_info)
                
    except Exception as e:
        logger.exception(e)
        
        
if __name__ == '__main__':
    main()    
    

