import argparse
import uuid
from rich import print
import httpx
from typing import Optional
from pydantic import ValidationError

from config.config import settings
from logger import logger
from property.property_actions_model import *

class FastAPIClient:
    def __init__(self, base_url: str, timeout: Optional[float] = 240.0):
        """
        Initialize the FastAPI client.

        :param base_url: The base URL of the FastAPI server
        :param timeout: Request timeout in seconds
        """
        
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def fetch_property(self, request: FetchPropertyRequest) -> FetchPropertyResponse:
        """
        Call the /fetch_property endpoint.

        :param request: FetchPropertyRequest object
        :return: FetchPropertyResponse object
        :raises: httpx.HTTPStatusError, ValidationError
        """
        url = "/fetch_property"
        try:
            response = self.client.post(url, json=request.model_dump())
            response.raise_for_status()
            return FetchPropertyResponse.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            print(f"HTTP error occurred: {exc.response.status_code} - {exc.response.text}")
            raise
        except ValidationError as exc:
            print(f"Response validation error: {exc}")
            raise

def main():
    # Parse Args
    parser = argparse.ArgumentParser(description='Editora Property client')
    parser.add_argument('-a', '--address', required=True, type=str, help='Property address')
    
    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument('-l', '--local', action='store_true', help='Route request to local instance')
    url_group.add_argument('-c', '--cloud', action='store_true', help='Route request to cloud service')
    
    args = parser.parse_args()
    LOCAL_HOST='0.0.0.0'
    PORT='8080'
    local_url = f'http://{LOCAL_HOST}:{PORT}'
    cloud_url = 'https://editora-v2-property-1095143658629.us-central1.run.app'
    
    if args.cloud:
        client = FastAPIClient(base_url=cloud_url)
    elif args.local:
        client = FastAPIClient(base_url=local_url)
    else:
        logger.error("No destination to route request to")
        return
    
    try:
        # Fetch Property
        fetch_property_request = FetchPropertyRequest(
            request_id=str(uuid.uuid4()),
            property_address=args.address
        )
    
        fetch_property_response = client.fetch_property(request=fetch_property_request)
        print(fetch_property_response)
        
    except Exception as e:
        logger.error(e)
        
if __name__ == '__main__':
    main()