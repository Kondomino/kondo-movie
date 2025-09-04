import requests
from bs4 import BeautifulSoup
import json
import jmespath
import argparse
from rich import print

from scrapfly import ScrapeConfig, ScrapflyClient

from logger import logger
from config.config import settings
from property.scrapers.scraper_base import ScraperBase
from property.property_model import PropertyModel
from property.address import Address
from gcp.secret import secret_mgr

class Zillow(ScraperBase):
    def __init__(self):
        self.scrapfly_client = ScrapflyClient(key=secret_mgr.secret(settings.Secret.SCRAPFLY_API_KEY))
    
    def get_property_info(self, address_obj:Address, debug=False)->PropertyModel.MLSInfo:
        
        logger.info(f"{self.__class__.__name__} - Fetching listing information for property address : {address_obj.input_address}")

        for address in address_obj.plausible_address_matches():
            
            logger.debug(f"Attempting to fetch listing from address variation - {address}")
            
            url = f'https://www.zillow.com/homes/for_sale/{address}/'
            
            try:
                # send a request to the search API
                search_api_response = self.scrapfly_client.scrape(
                    ScrapeConfig(url, country="US", asp=True)
                )
                search_api_response.raise_for_result()
                
                data = search_api_response.selector.css("script#__NEXT_DATA__::text").get()
                if data:
                    # Option 1: some properties are located in NEXT DATA cache
                    data = json.loads(data)
                    if debug:
                        with open('playground/output/zillow_data.json', 'w') as fp:
                            json.dump(data, fp, indent=2)
                    property_data = json.loads(data["props"]["pageProps"]["componentProps"]["gdpClientCache"])
                    property_data = property_data[list(property_data)[0]]['property']
                    if debug:
                        with open('playground/output/zillow_property_data.json', 'w') as fp:
                            json.dump(property_data, fp, indent=2)
                else:
                    # Option 2: other times it's in Apollo cache
                    data = search_api_response.selector.css("script#hdpApolloPreloadedData::text").get()
                    if not data:
                        continue
                    data = json.loads(json.loads(data)["apiCache"])
                    if debug:
                        with open('playground/output/zillow_data.json', 'w') as fp:
                            json.dump(data, fp, indent=2)
                    property_data = next(v["property"] for k, v in data.items() if "ForSale" in k)
                    if debug:
                        with open('playground/output/zillow_property_data.json', 'w') as fp:
                            json.dump(property_data, fp, indent=2)
            
                return self._extract_listing_info_json(property=property_data)
                
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
            
        logger.warning(f"Zillow failed to fetch listing - {address_obj.formatted_address}")
        return None
            
    def _extract_listing_info_json(self, property:dict)->PropertyModel.MLSInfo:

        mls_id = jmespath.search('attributionInfo.mlsId', property)
        list_price = jmespath.search('price', property)
        description = jmespath.search('description', property)
        
        # Extract status from various possible locations
        status = (jmespath.search('homeStatus', property) or 
                 jmespath.search('listingStatus', property) or
                 jmespath.search('mlsStatus', property) or
                 jmespath.search('marketingStatus', property))
        
        # Default to "Active" if no status found and property has price
        if not status and list_price:
            status = "Active"
        # Photos 
        expression = "responsivePhotos[].sort_by(mixedSources.jpeg, &width)[-1].url"
        media_urls = jmespath.search(expression=expression, data=property)
        
        specs = {}
        specs['property_type'] = jmespath.search("homeType", property)
        specs['beds'] = jmespath.search('bedrooms', property)
        specs['bath'] = jmespath.search('bathrooms', property)
        specs['living_size'] = jmespath.search('livingArea', property)
        specs['lot_size'] = jmespath.search('lotSize', property)
        
        return PropertyModel.MLSInfo(
            mls_id=mls_id,
            list_price=str(list_price),
            description=description,
            specs=specs,
            media_urls=media_urls,
            status=status
        )

# For testing purposes only
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Zillow Scraper')

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
        engine = Zillow()
        
        mls_info = engine.get_property_info(
            address_obj=address, 
            debug=True if args.debug else False)
        print(mls_info)
                
    except Exception as e:
        logger.exception(e)
        
        
if __name__ == '__main__':
    main()    
    

