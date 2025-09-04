import re
import requests
from bs4 import BeautifulSoup
import json
import jmespath
import argparse
from rich import print

from logger import logger
from config.config import settings
from property.scrapers.scraper_base import ScraperBase
from property.property_model import PropertyModel
from property.address import Address

class Compass(ScraperBase):
    def __init__(self):
        pass
    
    def get_property_info(self, address_obj:Address)->PropertyModel.MLSInfo:
        
        logger.info(f"{self.__class__.__name__} - Fetching listing information for property address : {address_obj.input_address}")

        for address in address_obj.plausible_address_matches():
            
            logger.debug(f"Attempting to fetch listing from address variation - {address}")
            
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
                    f"HTTP request succeeded\n{extra}"
                )

                response_json = response.json()
                if not jmespath.search('categories', response_json):
                    continue

                url = (
                    "https://www.compass.com"
                    + response_json["categories"][0]["items"][0]["redirectUrl"]
                )
                
                response = requests.get(url, headers=self.HEADERS)
                soup = BeautifulSoup(response.content, 'html.parser')
                
                
                script_tag = soup.find("script", string=re.compile(r"window\.__PARTIAL_INITIAL_DATA__"))
                
                # Extract the full text of that script
                script_text = script_tag.get_text(strip=True)
                
                # Regex pattern to capture the JSON after __PARTIAL_INITIAL_DATA__
                pattern = r"window\.__(\w+)__\s*=\s*(.*)"
                match = re.search(pattern, script_text, flags=re.DOTALL)
                if not match:
                    logger.error("Could not extract JSON data from __PARTIAL_INITIAL_DATA__")
                    continue

                # The JSON portion
                json_str = match.group(2)
                json_data = json.loads(json_str)
                return self._extract_listing_info_json(json_data=json_data)
                
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
                return None
            except ValueError as ve:
                logger.error(ve)
                return None
            except Exception as e:
                logger.exception(e)
                return None
            
        logger.warning(f"Compass failed to fetch listing - {address_obj.formatted_address}")
        return None
            
    def _extract_listing_info_json(self, json_data:dict)->PropertyModel.MLSInfo:
        listing = jmespath.search('props.listingRelation.listing', json_data) 
        
        mls_id = jmespath.search('externalId', listing)
        list_price = jmespath.search('price.lastKnown', listing)
        description = jmespath.search('description', listing)
        photos_sub_path = jmespath.search('media', listing)
        media_urls = [jmespath.search('originalUrl', photo) for photo in photos_sub_path] \
            if photos_sub_path else []
        
        specs = {}
        specs['property_type'] = jmespath.search("detailedInfo.keyDetails[?key=='Compass Type'].value | [0]", listing)
        specs['beds'] = jmespath.search('size.bedrooms', listing)
        specs['bath'] = jmespath.search('size.bathrooms', listing)
        specs['living_size'] = jmespath.search('size.squareFeet', listing)
        specs['lot_size'] = jmespath.search('size.lotSizeInSquareFeet', listing)
        
        return PropertyModel.MLSInfo(
            mls_id=mls_id,
            list_price=str(list_price),
            description=description,
            specs=specs,
            media_urls=media_urls,
        )

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
    
