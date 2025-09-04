import json
import jmespath
import argparse
import requests
from rich import print

from redfin import Redfin
from logger import logger
from config.config import settings
from property.scrapers.scraper_base import ScraperBase
from property.property_model import PropertyModel
from property.address import Address

class RedfinEngine(ScraperBase):
    def __init__(self):
        self.client = Redfin()
        self.client.user_agent_header = self.HEADERS
        
    def get_property_info(self, address_obj:Address)->PropertyModel.MLSInfo:
        
        logger.info(f"{self.__class__.__name__} - Fetching listing information for property address : {address_obj.input_address}")
        
        try:
            for address in address_obj.plausible_address_matches():
                logger.debug(f"Attempting to fetch listing from address variation - {address}")
                response = self.client.search(address)
                url = jmespath.search('payload.exactMatch.url', response)
                if not url:
                    url = jmespath.search('payload.sections[0].rows[0].url', response)
                    if not url:
                        continue
                
                
                initial_info = self.client.initial_info(url)
                property_id = jmespath.search('payload.propertyId', initial_info)
                listing_id = jmespath.search('payload.listingId', initial_info)
                
                if not property_id or not listing_id:
                    continue

                mls_data_above_the_fold = self.client.above_the_fold(property_id=property_id, listing_id=listing_id)                        
                mls_data_below_the_fold = self.client.below_the_fold(property_id=property_id)
                    
                return self.extract(
                    mls_data_above_the_fold=mls_data_above_the_fold,
                    mls_data_below_the_fold=mls_data_below_the_fold
                )
        
        except requests.exceptions.HTTPError as he:
            extra={
                    "status_code": he.response.status_code,
                    "reason": he.response.reason,
                    "response_body": he.response.text
                }
            logger.error(
                f"HTTP request failed\n{extra}",
            )
        except json.decoder.JSONDecodeError as je:
            logger.warning("Couldn't decode JSON object in response. Potential rate limit by Redfin?")
            
        except Exception as e:
            logger.warning(e)
            
        return None
    
    def extract(self, mls_data_above_the_fold:dict, mls_data_below_the_fold:dict)->PropertyModel.MLSInfo:
        mls_id = jmespath.search('payload.propertyHistoryInfo.events[0].sourceId', mls_data_below_the_fold)
        list_price = jmespath.search('payload.addressSectionInfo.priceInfo.amount', mls_data_above_the_fold)
        description = jmespath.search('payload.propertyHistoryInfo.events[0]\
            .marketingRemarks[0].marketingRemark', mls_data_below_the_fold)
        photos_sub_path = jmespath.search('payload.mediaBrowserInfo.photos', mls_data_above_the_fold)
        media_urls = [jmespath.search('photoUrls.fullScreenPhotoUrl', photo) for photo in photos_sub_path] \
            if photos_sub_path else []
        
        specs = {}
        specs['property_type'] = jmespath.search('payload.publicRecordsInfo.basicInfo.propertyTypeName', mls_data_below_the_fold)
        specs['beds'] = jmespath.search('payload.addressSectionInfo.beds', mls_data_above_the_fold)
        specs['bath'] = jmespath.search('payload.addressSectionInfo.baths', mls_data_above_the_fold)
        specs['living_size'] = jmespath.search('payload.addressSectionInfo.sqFt.value', mls_data_above_the_fold)
        specs['lot_size'] = jmespath.search('payload.addressSectionInfo.lotSize', mls_data_above_the_fold)
        
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
    parser = argparse.ArgumentParser(description='Redfin Scraper')

    parser.add_argument('-a', '--address', required=True, type=str, help='Property address to search for')
    
    args = parser.parse_args()
    address = Address(args.address)
    
    try:
        engine = RedfinEngine()
        mls_info = engine.get_property_info(address)
        print(mls_info)
                
    except Exception as e:
        logger.exception(e)
        
        
if __name__ == '__main__':
    main()    
    