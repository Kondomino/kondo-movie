import requests
from bs4 import BeautifulSoup
import json
from functools import reduce

from logger import logger
from config.config import settings
from property.scrapers.scraper_base import ScraperBase
from property.property_model import PropertyModel
from property.address import Address
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse
from rich import print

WORKING_DIR = 'Editor/Playground/Property'
PROPERTY_DETAILS_FILE = 'property.json'

class ColdwellBanker(ScraperBase):
    def __init__(self):
        pass
        
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
    }
    
    def get_property_info(self, address_obj:Address)->PropertyModel:
        
        address = str(address_obj)

        logger.info(f"Fetching listing information for property address : {address}")
        
        # Send a GET request to the URL (Make sure you comply with website's TOS)
        
        
        WORD_REPLACEMENTS = {
            "drive": "dr",
            "street": "st",
            "road": "rd",
            "boulevard": "blvd",
            "terrace": "tce",
            "place": "pl",
            "avenue": "ave",
            "lane": "ln",
            "apartment": "apt",
            "suite": "ste",
            "ct": "court", # ==> Coldwell Hack? 'Ct' is not recognized by the API URL. E.g. 9917 Rothschild Ct, Clearcreek Twp, OH 45458
            "highway": "hwy",
            "meadows": "mdws",
        }
        # preprocess address
        address = address.lower()
        for find, replace in WORD_REPLACEMENTS.items():
            address = address.replace(find, replace)

        logger.debug("Pre-processed address: {}", address)

        # search listings
        url = (
            f"https://www.coldwellbanker.com/api/suggest/property,listing/{address}"
        )
        
        logger.debug(f"URL: {url}")
        
        listing_id = None
        response = requests.get(url, headers=ColdwellBanker.HEADERS)
        try:
            response.raise_for_status()
            logger.debug(
                "HTTP request succeeded",
                extra={
                    "url": url,
                    "status_code": response.status_code,
                    "response_body": response.text
                }
            )
            search_resp_json = response.json()
            if (
                not search_resp_json["results"]
                or not search_resp_json["results"][0]["entityType"] == "property"
            ):
                raise ValueError(f"Unable to process JSON response to fetch listing URL. Response : {search_resp_json}")

            # scrape the first result
            listing_id = search_resp_json['results'][0]['suggestions'][0]['listingId']
            listing_url = f"https://www.coldwellbanker.com{search_resp_json['results'][0]['suggestions'][0]['canonicalListingURL']}"

        except requests.exceptions.HTTPError as he:
            logger.error(
                "HTTP request failed",
                extra={
                    "url": url,
                    "status_code": he.response.status_code,
                    "reason": he.response.reason,
                    "response_body": he.response.text
                }
            )
            return None
        except ValueError as ve:
            logger.error(ve)
            return None
        except Exception as e:
            logger.exception(e)
            return None
            
        try:
            response = requests.get(listing_url, headers=ColdwellBanker.HEADERS)
            response.raise_for_status()
            
            # Parse the HTML content using BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            description, media, specs = self._extract_listing_info_json(soup=soup)
        
            return PropertyModel(
                id=address_obj.place_id,
                mls_id=listing_id,
                address=address,
                description=description,
                extraction_engine=str(ColdwellBanker.__name__),
                extraction_time=datetime.now(tz=ZoneInfo(settings.General.TIMEZONE)),
                media=media, 
                specs=specs)
            
        except requests.exceptions.HTTPError as he:
            logger.error(
                "HTTP request failed",
                extra={
                    "url": url,
                    "status_code": he.response.status_code,
                    "reason": he.response.reason,
                    "response_body": he.response.text
                }
            )
            return None
        except ValueError as ve:
            logger.error(ve)
            return None
        except Exception as e:
            logger.exception(e)
            return None
            
    def _extract_listing_info_json(self, soup:BeautifulSoup)->tuple[str, list, dict]:
        def _get_nested(data, keys, default=None):
            """
            Retrieve a nested value using reduce.

            :param data: The dictionary to traverse.
            :param keys: A list of keys representing the path.
            :param default: The default value if the path is not found.
            :return: The retrieved value or the default.
            """
            return reduce(lambda d, key: d.get(key, default) if isinstance(d, dict) else default, keys, data)
        
        def _extract_property_specs(property_details:dict) -> dict:
            unparsed_address = _get_nested(property_details, ['address', 'unparsedAddress'])
            city = _get_nested(property_details, ['address', 'city'])
            num_bed = _get_nested(property_details, ['summary', 'bedroomsTotal'])
            num_bath = _get_nested(property_details, ['summary', 'bathroomsTotal'])
            living_size = _get_nested(property_details, ['summary', 'listingSqFt'])
            lot_size = _get_nested(property_details, ['lot', 'lotSizeSquareFeet'])
            property_type = _get_nested(property_details, ['about', 'homeFacts', 'propertyType'])
            list_price = _get_nested(property_details, ['finances', 'finances', 'listPrice'])
            
            return {
                'property_type': property_type,
                'unparsed_address': unparsed_address,
                'city': city,
                'beds': num_bed,
                'bath': num_bath,
                'living_size': living_size,
                'lot_size': lot_size,
                'list_price': list_price
            }

        # Find the <script> tag with the specific id and type
        script_tag = soup.find('script', id='__NEXT_DATA__', type='application/json')
        
        # Check if the script tag was found
        if script_tag:
            # Extract the JSON string from the script tag
            json_str = script_tag.string

            # Parse the JSON string into a Python dictionary
            json_data = json.loads(json_str)
            property_details = _get_nested(json_data, ['props', 'pageProps', 'propertyDetails'])
            
            with open(f'{WORKING_DIR}/{PROPERTY_DETAILS_FILE}', "w") as f:
                json.dump(property_details, f, indent=4)
                                           
            description = _get_nested(property_details, ['about', 'description'])
            
            image_urls = []
            source = []
            
            images = _get_nested(property_details, ['media', 'images'])
            if images:
                image_urls = [image['mediaUrl'] for image in images]
            for image_url in image_urls:
                source.append(PropertyModel.Media.Image(url=image_url))
            media = PropertyModel.Media(source=source)
            
            specs = _extract_property_specs(property_details=property_details)
            
            return description, media, specs
        else:
            raise ValueError("Property description script tag not found")

    def _extract_listing_info_html(self, soup:BeautifulSoup)->tuple[str, list]:
        
        description = None
        image_urls = []
        
        
        # DESCRIPTION
        # Find the <script> tag with id 'property-residence' and type 'application/ld+json'
        script_tag = soup.find('script', id='property-residence', type='application/ld+json')

        if script_tag:
            # Extract the JSON content
            json_content = script_tag.string

            # Parse the JSON content
            data = json.loads(json_content)

            # Extract the 'description' field
            description = data.get('description', 'Description not found.')
            logger.debug(f"DESCRIPTION : {description}")
        else:
            raise ValueError("Property description script tag not found")

        # TITLE
        # extract address as title
        title_divs = soup.find_all("div", {"data-testid": "address"})
        if title_divs:
            title = title_divs[0].get_text(" ", strip=True)
            logger.debug(f"TITLE : {title}")
        else:
            raise ValueError("Could not extract title")

        # IMAGES 
        img_tags = soup.find_all("img")
        if img_tags:
            listing_img_tags = [
                img_tag for img_tag in img_tags if img_tag["alt"].startswith("Listing")
            ]
            
            if listing_img_tags:
                try:
                    listing_images_dir_url = listing_img_tags[0]["src"][
                        :-6
                    ]  # remove last part with extension
                except (IndexError, KeyError) as exc:
                    logger.error("Error while scraping: {}", str(exc))
                    raise exc

                for i in range(settings.Property.IMAGE_LIMIT):
                    try:
                        url = listing_images_dir_url + str(i).zfill(2) + ".jpg"
                        image_resp = requests.get(
                            url, headers=ColdwellBanker.HEADERS, allow_redirects=True, timeout=15
                        )
                        image_resp.raise_for_status()
                        image_urls.append(url)
                    except requests.RequestException as exc:
                        if exc.response and exc.response.status_code == 404:
                            # ran out of images
                            break
                        logger.debug("could not download image from: {}. Exc: {}", url, str(exc))
                        continue
                
                logger.info(f"Detected {len(image_urls)} images for listing")
            
                source = []
                for image_url in image_urls:
                    source.append(PropertyModel.Media.Image(url=image_url))
                media = PropertyModel.Media(source=source)
                
                return description, media

        raise ValueError("Could not find image tags")
    
    
def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Coldwell Banker')
    parser.add_argument('-a', '--address', required=True, type=str, help='Address')
    
    args = parser.parse_args()
    
    engine = ColdwellBanker()
    model = engine.get_property_info(Address(args.address))
    print(model)
    
if __name__ == '__main__':
    main()
    


