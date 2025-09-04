import requests
import argparse
import hashlib
from enum import Enum
from rich import print

import usaddress

from logger import logger
from config.config import settings
from gcp.secret import secret_mgr

class Address:        
    KEY_ID = 'id'
    KEY_TYPES = 'types'
    KEY_PRIMARY_TYPE = 'primaryType'
    KEY_FORMATTED_ADDRESS = 'formattedAddress'
    KEY_SHORT_FORMATTED_ADDRESS = 'shortFormattedAddress'
    KEY_ADDRESS_COMPONENTS = 'addressComponents'
    
    
    class AddressInputType(Enum):
        AutoComplete = "AutoComplete"
        FreeForm = "FreeForm"
        PropertyTitle = "PropertyTitle"

    def __init__(self, address:str, address_input_type:AddressInputType=AddressInputType.AutoComplete, tenant_id:str=None):
        logger.info(f"[ADDRESS] Initializing Address object with input: '{address}', type: {address_input_type.name}, tenant: {tenant_id}")
        self.input_address = address
        self.address_input_type = address_input_type
        self.tenant_id = tenant_id
        self.primary_type = None
        self.types = None
        self.formatted_address = None
        self.place_id = None
        self.short_formatted_address = None
        self.formatted_address_without_country = None
        self.address_components = None
        
        if self.address_input_type == self.AddressInputType.AutoComplete:
            logger.info(f"[ADDRESS] Using AutoComplete parsing for address: '{address}'")
            self.parse_address_auto_complete()
        elif self.address_input_type == self.AddressInputType.FreeForm:
            logger.info(f"[ADDRESS] Using FreeForm parsing for address: '{address}'")
            self.parse_address_free_form()
        elif self.address_input_type == self.AddressInputType.PropertyTitle:
            logger.info(f"[ADDRESS] Using PropertyTitle parsing for address: '{address}'")
            self.parse_address_property_title()
        
        logger.info(f"[ADDRESS] Address parsing completed:")
        logger.info(f"[ADDRESS]   - Place ID: {self.place_id}")
        logger.info(f"[ADDRESS]   - Formatted Address: {self.formatted_address}")
        logger.info(f"[ADDRESS]   - Short Formatted Address: {self.short_formatted_address}")
        logger.info(f"[ADDRESS]   - Address Components: {len(self.address_components) if self.address_components else 0} components")
    
    def parse_address_auto_complete(self)->None:
        # Check if Google Maps API is enabled
        if not settings.FeatureFlags.ENABLE_GOOGLE_MAPS:
            logger.warning(f"[ADDRESS] Google Maps API disabled - using basic address parsing for: '{self.input_address}'")
            self._use_basic_address_parsing()
            return
            
        # Step 1: Find Place ID
        find_place_url = 'https://places.googleapis.com/v1/places:searchText'
        headers = {
            'Content-Type': 'application/json',
            'X-Goog-Api-Key': secret_mgr.secret(settings.Secret.GOOGLE_MAPS_API_KEY),
            'X-Goog-FieldMask': 'places.id'
        }
        data = {
            'textQuery': self.input_address
        }

        logger.info(f"[ADDRESS] Calling Google Places API with textQuery: '{self.input_address}'")
        try:
            response = requests.post(find_place_url, headers=headers, json=data)
            response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
            result = response.json()
            response_data = response.json()

            logger.info(f"[ADDRESS] Google Places API response status: {response.status_code}")
            logger.info(f"[ADDRESS] Google Places API response: {response_data}")

            if 'places' in response_data and response_data['places']:
                self.place_id = response_data['places'][0]['id']
                logger.info(f"[ADDRESS] Found place_id: {self.place_id}")
                
                # Step 2: Get Place Details
                base_url = f'https://places.googleapis.com/v1/places/{self.place_id}'
                # Request headers
                field_mask = f'{self.KEY_ID},{self.KEY_PRIMARY_TYPE},{self.KEY_TYPES},{self.KEY_FORMATTED_ADDRESS},{self.KEY_SHORT_FORMATTED_ADDRESS},{self.KEY_ADDRESS_COMPONENTS}'
                headers = {
                    'Content-Type': 'application/json',
                    'X-Goog-Api-Key': secret_mgr.secret(settings.Secret.GOOGLE_MAPS_API_KEY),
                    'X-Goog-FieldMask': field_mask
                }
                
                logger.info(f"[ADDRESS] Calling Google Places Details API for place_id: {self.place_id}")
                # Step 2 : Fetch formatted address
                response = requests.get(base_url, headers=headers)
                response.raise_for_status()  # Raises HTTPError for bad responses (4xx or 5xx)
                result = response.json()
                logger.info(f"[ADDRESS] Google Places Details API response: {result}")
                
                self.formatted_address = result[self.KEY_FORMATTED_ADDRESS]
                self.short_formatted_address = result[self.KEY_SHORT_FORMATTED_ADDRESS]
                self.address_components = result[self.KEY_ADDRESS_COMPONENTS]

                # Generate formatted addresses without country using consistent method
                self._set_formatted_addresses_from_short_forms()
            else:
                logger.warning(f"[ADDRESS] No places found for address: '{self.input_address}' - falling back to basic parsing")
                self._use_basic_address_parsing()
        except Exception as e:
            logger.error(f"[ADDRESS] Google Places API failed: {str(e)} - falling back to basic parsing")
            self._use_basic_address_parsing()
            
            logger.info(f"[ADDRESS] Parsed address details:")
            logger.info(f"[ADDRESS]   - Formatted Address: {self.formatted_address}")
            logger.info(f"[ADDRESS]   - Short Formatted Address: {self.short_formatted_address}")
            logger.info(f"[ADDRESS]   - Formatted Address without Country: {self.formatted_address_without_country}")
        else:
            logger.warning(f"[ADDRESS] No places found in Google Places API response for address: '{self.input_address}'")
            self.formatted_address = self.input_address
            self.place_id = hashlib.sha256(self.formatted_address.encode("utf-8")).hexdigest()
            
            # Generate formatted addresses without country using consistent method
            self._set_formatted_addresses_from_short_forms()
            
            self.address_components = None
    
    def _set_formatted_addresses_from_short_forms(self):
        """
        Helper method to consistently set formatted addresses from short_forms dictionary.
        This ensures consistent behavior across all parsing methods.
        """
        try:
            short_forms = self.gen_short_forms(self.formatted_address)
            if short_forms and isinstance(short_forms, dict):
                # Use .get() for safe dictionary access with fallbacks
                self.formatted_address_without_country = short_forms.get('formatted_address_without_country', self.formatted_address)
                # Note: short_formatted_address is already set from Google Places API
                # Only update it if we're not using AutoComplete parsing
                if self.address_input_type != self.AddressInputType.AutoComplete:
                    self.short_formatted_address = short_forms.get('short_formatted_address', self.formatted_address)
                logger.debug(f"[ADDRESS] Set formatted addresses from short_forms: {short_forms}")
            else:
                # Fallback to using the formatted address
                self.formatted_address_without_country = self.formatted_address
                if self.address_input_type != self.AddressInputType.AutoComplete:
                    self.short_formatted_address = self.formatted_address
                logger.warning(f"[ADDRESS] No valid short_forms returned, using fallback addresses")
        except Exception as e:
            logger.warning(f"[ADDRESS] Error setting formatted addresses from short_forms: {str(e)}")
            # Fallback to using the formatted address
            self.formatted_address_without_country = self.formatted_address
            if self.address_input_type != self.AddressInputType.AutoComplete:
                self.short_formatted_address = self.formatted_address
    
    def parse_address_free_form(self)->None:
        """
        Parse a free-form address using the usaddress library.
        This method is used when the address is not provided through Google Places API.
        It attempts to parse the address into components and format it appropriately.
        """
        try:
            # Parse the address using usaddress
            parsed_address, address_type = usaddress.tag(self.input_address)
            
            # Generate a unique place_id using the input address
            self.place_id = hashlib.sha256(self.input_address.encode("utf-8")).hexdigest()
            
            # Set the formatted address to the input address
            self.formatted_address = self.input_address
            
            # Store the parsed address components
            self.address_components = parsed_address
            
            # Set primary type and types based on address_type
            self.primary_type = address_type
            self.types = [address_type]
            
            # Generate formatted addresses without country using consistent method
            self._set_formatted_addresses_from_short_forms()
            
            logger.info(f"Successfully parsed free-form address: {self.formatted_address}")
            
        except Exception as e:
            logger.warning(f"Failed to parse free-form address '{self.input_address}': {e}")
            # Fallback to using the input address as is
            self.formatted_address = self.input_address
            self.place_id = hashlib.sha256(self.formatted_address.encode("utf-8")).hexdigest()
            
            # Generate formatted addresses without country using consistent method
            self._set_formatted_addresses_from_short_forms()
            
            self.address_components = None
            self.primary_type = None
            self.types = None
    
    def parse_address_property_title(self)->None:
        """
        Parse a property title (e.g., "BRENTWOOD PRIVATE ESTATE", "WEST HOLLYWOOD").
        This method is used when the input is a property title rather than a physical address.
        It treats the input as a title and generates appropriate identifiers.
        """
        try:
            # Generate a unique place_id using the input title
            self.place_id = hashlib.sha256(self.input_address.encode("utf-8")).hexdigest()
            
            # Set the formatted address to the input title
            self.formatted_address = self.input_address
            
            # For property titles, we don't have traditional address components
            self.address_components = None
            self.primary_type = "property_title"
            self.types = ["property_title"]
            
            # For property titles, use the title as the formatted address
            self.formatted_address_without_country = self.input_address
            self.short_formatted_address = self.input_address
            
            logger.info(f"Successfully parsed property title: {self.formatted_address}")
            
        except Exception as e:
            logger.warning(f"Failed to parse property title '{self.input_address}': {e}")
            # Fallback to using the input title as is
            self.formatted_address = self.input_address
            self.place_id = hashlib.sha256(self.formatted_address.encode("utf-8")).hexdigest()
            self.formatted_address_without_country = self.input_address
            self.short_formatted_address = self.input_address
            self.address_components = None
            self.primary_type = "property_title"
            self.types = ["property_title"]
    
    def gen_short_forms(self, formatted_address:str)->dict:
        """
        Generate formatted addresses without the country using usaddress.
        Handles apartment addresses by including secondary address components.
        
        Args:
            formatted_address: The full formatted address including country
            
        Returns:
            A dictionary containing:
            - formatted_address_without_country: The formatted address without the country
            - short_formatted_address: The street address with secondary components and city, but without state, zip, or country
        """
        try:
            # Parse the address using usaddress
            parsed_address, _ = usaddress.tag(formatted_address)
            
            # Extract components we want to keep
            components = []
            
            # Add house number and street name if available
            if 'AddressNumber' in parsed_address:
                components.append(parsed_address['AddressNumber'])
            if 'StreetName' in parsed_address:
                components.append(parsed_address['StreetName'])
            if 'StreetNamePostType' in parsed_address:
                components.append(parsed_address['StreetNamePostType'])
                
            # Add secondary address components (apartment, suite, etc.)
            secondary_components = []
            if 'OccupancyType' in parsed_address:
                secondary_components.append(parsed_address['OccupancyType'])
            if 'OccupancyIdentifier' in parsed_address:
                secondary_components.append(parsed_address['OccupancyIdentifier'])
                
            # Add city if available
            city = None
            if 'PlaceName' in parsed_address:
                city = parsed_address['PlaceName']
                components.append(city)
                
            # Add state if available
            if 'StateName' in parsed_address:
                components.append(parsed_address['StateName'])
                
            # Add zip code if available
            if 'ZipCode' in parsed_address:
                components.append(parsed_address['ZipCode'])
                
            # Join components with appropriate separators
            street_part = ' '.join([c for c in components[:3] if c])
            
            # Add secondary address components if available
            if secondary_components:
                street_part += ', ' + ' '.join(secondary_components)
                
            city_state_zip = ', '.join([c for c in components[3:] if c])
            
            # Combine parts for formatted_address_without_country
            if city_state_zip:
                formatted_address_without_country = f"{street_part}, {city_state_zip}"
            else:
                formatted_address_without_country = street_part
                
            # For short_formatted_address, include street part and city
            if city:
                short_formatted_address = f"{street_part}, {city}"
            else:
                short_formatted_address = street_part
                
            return {
                'formatted_address_without_country': formatted_address_without_country,
                'short_formatted_address': short_formatted_address
            }
            
        except Exception as e:
            logger.warning(f"Failed to parse address '{formatted_address}' with usaddress: {e}")
            # Fallback to the original method
            address_parts = formatted_address.split(",")
            if len(address_parts) > 1:
                address_parts.pop(-1)  # Remove the last part (country)
            formatted_address_without_country = ",".join(address_parts).strip()
            
            # For short formatted address, use the first two parts (street address and city)
            if len(address_parts) >= 2:
                short_formatted_address = f"{address_parts[0].strip()}, {address_parts[1].strip()}"
            else:
                short_formatted_address = address_parts[0].strip() if address_parts else formatted_address_without_country
            
            return {
                'formatted_address_without_country': formatted_address_without_country,
                'short_formatted_address': short_formatted_address
            }
            
    def plausible_address_matches(self)->list[str]:
        """
        Returns a list of plausible address matches, removing any duplicates.
        
        Returns:
            A list of unique address strings
        """
        # Create a list of all possible address formats
        if self.address_input_type == self.AddressInputType.FreeForm:
            all_addresses = [
                self.formatted_address, # Same as input address
                self.formatted_address_without_country,
            ]
        elif self.address_input_type == self.AddressInputType.PropertyTitle:
            all_addresses = [
                self.formatted_address, # Property title
                self.input_address
            ]
        else:  # AutoComplete
            all_addresses = [
                self.formatted_address_without_country,
                self.formatted_address,
                self.input_address
            ]
        
        # Remove duplicates while preserving order
        unique_addresses = []
        for address in all_addresses:
            if address and address not in unique_addresses:
                unique_addresses.append(address)
                
        return unique_addresses
    
    def _use_basic_address_parsing(self):
        """
        Fallback method for basic address parsing when Google Maps API is disabled.
        Uses simple string manipulation to extract address components.
        """
        logger.info(f"[ADDRESS] Using basic address parsing for: '{self.input_address}'")
        
        # Set basic fields
        self.place_id = None
        self.formatted_address = self.input_address
        self.primary_type = None
        self.types = None
        self.address_components = None
        
        # Try to create a reasonable short formatted address
        # Split by comma and take first two parts (street + city)
        parts = self.input_address.split(',')
        if len(parts) >= 2:
            self.short_formatted_address = f"{parts[0].strip()}, {parts[1].strip()}"
            self.formatted_address_without_country = ', '.join(part.strip() for part in parts[:-1]) if len(parts) > 2 else self.input_address
        else:
            self.short_formatted_address = self.input_address
            self.formatted_address_without_country = self.input_address
        
        logger.info(f"[ADDRESS] Basic parsing results:")
        logger.info(f"[ADDRESS]   - Formatted Address: {self.formatted_address}")
        logger.info(f"[ADDRESS]   - Short Formatted Address: {self.short_formatted_address}")
        logger.info(f"[ADDRESS]   - Formatted Address without Country: {self.formatted_address_without_country}")
        
            
    def __str__(self):
        return self.formatted_address
            
if __name__ == '__main__':
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Google Places')

    parser.add_argument('-a', '--address', required=True, type=str, help='Address')
    parser.add_argument('-d', '--debug', action='store_true', help='Debug mode')
    parser.add_argument('-t', '--type', choices=['autocomplete', 'freeform', 'propertytitle'], default='freeform', 
                        help='Address input type: autocomplete (uses Google Places API), freeform (uses usaddress), or propertytitle (for property titles)')
    
    args = parser.parse_args()
    
    # Convert string input type to enum
    if args.type == 'autocomplete':
        input_type = Address.AddressInputType.AutoComplete
    elif args.type == 'propertytitle':
        input_type = Address.AddressInputType.PropertyTitle
    else:
        input_type = Address.AddressInputType.FreeForm
    
    address = Address(args.address, input_type)
    
    logger.info(f"Input address: {address.input_address}")
    logger.info(f"Address input type: {address.address_input_type.name}")
    logger.info(f"Formatted address: {str(address)}")
    logger.info(f"Formatted address w/o country: {address.formatted_address_without_country}")
    logger.info(f"Short Formatted address: {address.short_formatted_address}")
    logger.info(f"Place ID: {address.place_id}")
    
    if args.debug and address.address_components:
        print(address.address_components)
        if address.primary_type:
            print(f"Primary Type: {address.primary_type}") 
        if address.types:
            print(f"Types: {address.types}")
            
    # Print plausible matches
    print("\nPlausible address matches:")
    for i, match in enumerate(address.plausible_address_matches(), 1):
        print(f"{i}. {match}")
        
