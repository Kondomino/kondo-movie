import requests
from bs4 import BeautifulSoup
import json
import jmespath
from functools import reduce

from logger import logger
from config.config import settings
from property.scrapers.scraper_base import ScraperBase
from property.property_model import PropertyModel
from property.address import Address
from gcp.secret import secret_mgr
from utils.str_utils import apply_street_abbreviations

class ColdwellBanker(ScraperBase):
    def __init__(self):
        pass
    
    def get_property_info(self, address_obj:Address)->PropertyModel.MLSInfo:
        
        logger.info(f"{self.__class__.__name__} - Fetching listing information for property address : {address_obj.input_address}")
        
        plausible_addr_matches = address_obj.plausible_address_matches()
        
        # Add variations using the utility function
        # Apply street abbreviations to formatted address
        f_address_abbrev = apply_street_abbreviations(address_obj.formatted_address).lower()
        if f_address_abbrev != address_obj.formatted_address.lower():
            plausible_addr_matches.append(f_address_abbrev)
            
        # Apply street abbreviations to input address
        i_address_abbrev = apply_street_abbreviations(address_obj.input_address).lower()
        if i_address_abbrev != address_obj.input_address.lower():
            plausible_addr_matches.append(i_address_abbrev)
        
        for address in plausible_addr_matches:
            
            logger.debug(f"Attempting to fetch listing from address variation - {address}")
            
            # search listings
            url = (
                f"https://www.coldwellbanker.com/api/suggest/property,listing/{address}"
            )
            
            response = requests.get(url, headers=ColdwellBanker.HEADERS)
            try:
                response.raise_for_status()
                extra={
                        "url": url,
                        "status_code": response.status_code,
                        "response_body": response.text
                    }
                logger.debug(
                    f"HTTP request succeeded\n{extra}"
                )
                
                search_resp_json = response.json()
                if jmespath.search("results[0].entityType", search_resp_json) == "property":
                    break
                
                logger.info(f"Addr '{address}' yielded no results. Trying other addr. matches")

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
            
        if not search_resp_json["results"] or not search_resp_json["results"][0]["entityType"] == "property":
            logger.warning(f"Coldwell Banker failed to fetch listing - {address_obj.formatted_address}")
            return None
        
        # Extract status from search results before going to detailed page
        search_status = search_resp_json['results'][0]['suggestions'][0].get('status')
        logger.info(f"[COLDWELL_BANKER] Found status in search results: {search_status}")
        
        # scrape the first result
        listing_url = f"https://www.coldwellbanker.com{search_resp_json['results'][0]['suggestions'][0]['canonicalListingURL']}"

        try:
            response = requests.get(listing_url, headers=ColdwellBanker.HEADERS)
            response.raise_for_status()
            
            # Parse the HTML content using BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')
            return self._extract_listing_info_json(soup=soup, search_status=search_status) 
            
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
            
    def _extract_listing_info_json(self, soup:BeautifulSoup, search_status:str=None)->PropertyModel.MLSInfo:
        def _get_nested(data, keys, default=None):
            """
            Retrieve a nested value using reduce.

            :param data: The dictionary to traverse.
            :param keys: A list of keys representing the path.
            :param default: The default value if the path is not found.
            :return: The retrieved value or the default.
            """
            return reduce(lambda d, key: d.get(key, default) if isinstance(d, dict) else default, keys, data)
        
        def _extract_listing_info(listing_data:dict) -> PropertyModel.MLSInfo:
            property_details = _get_nested(listing_data, ['props', 'pageProps', 'propertyDetails'])
            mls_id = _get_nested(property_details, ['about', 'mlsListingId'])
            description = _get_nested(property_details, ['about', 'description'])
            
            # Extract status - prioritize search_status, then try various locations in property details
            status = (search_status or
                     _get_nested(property_details, ['about', 'status']) or 
                     _get_nested(property_details, ['about', 'listingStatus']) or
                     _get_nested(property_details, ['finances', 'status']) or
                     _get_nested(property_details, ['summary', 'status']))
            
            logger.info(f"[COLDWELL_BANKER] Status extraction - search_status: {search_status}, final_status: {status}")
            
            media_urls = []
            images = _get_nested(property_details, ['media', 'images'])
            if images:
                media_urls = [image['mediaUrl'] for image in images]
            
            list_price = _get_nested(property_details, ['finances', 'finances', 'listPrice'])
            
            # Default to "Active" if no status found and property has price
            if not status and list_price:
                status = "Active"
            
            num_bed = _get_nested(property_details, ['summary', 'bedroomsTotal'])
            num_bath = _get_nested(property_details, ['summary', 'bathroomsTotal'])
            living_size = _get_nested(property_details, ['summary', 'listingSqFt'])
            lot_size = _get_nested(property_details, ['lot', 'lotSizeSquareFeet'])
            property_type = _get_nested(property_details, ['about', 'homeFacts', 'propertyType'])
            
            specs = {
                'property_type': property_type,
                'beds': num_bed,
                'bath': num_bath,
                'living_size': living_size,
                'lot_size': lot_size,
            }
            
            return PropertyModel.MLSInfo(
                mls_id=mls_id,
                list_price=list_price,
                description=description,
                specs=specs,
                media_urls=media_urls,
                status=status
            )

        # Find the <script> tag with the specific id and type
        script_tag = soup.find('script', id='__NEXT_DATA__', type='application/json')
        
        # Check if the script tag was found
        if script_tag:
            # Extract the JSON string from the script tag
            json_str = script_tag.string
            json_data = json.loads(json_str)
            return _extract_listing_info(listing_data=json_data)
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


