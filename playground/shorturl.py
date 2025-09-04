import argparse
import requests
from rich import print

from config.config import settings
from gcp.secret import secret_mgr

def gen_short_url(long_url: str)->str:
    API_KEY = secret_mgr.secret(secret_id=settings.Secret.SHORTIO_API_KEY)
    DOMAIN = 'l.editora.ai'
    
    res = requests.post(
        'https://api.short.io/links/public', 
        json={
            'domain': DOMAIN,
            'originalURL': long_url,
        }, 
        headers = {
            'authorization': API_KEY,
            'content-type': 'application/json'
        } 
    )

    res.raise_for_status()
    data = res.json()

    print(data)

def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Short URL Generator")

    # Create a mutually exclusive group to ensure user chooses either file or directory mode, not both
    parser.add_argument("-u", "--url", type=str, required=True, help="URL to shorten")
    args = parser.parse_args()
    
    gen_short_url(long_url=args.url)

if __name__ == '__main__':
    main()