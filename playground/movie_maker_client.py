import argparse
import uuid
from rich import print
import httpx
from typing import Optional
from pydantic import ValidationError

from movie_maker.movie_actions_model import *
from config.config import settings
from logger import logger

class FastAPIClient:
    def __init__(self, base_url: str, timeout: Optional[float] = 240.0):
        """
        Initialize the FastAPI client.

        :param base_url: The base URL of the FastAPI server (e.g., 'http://localhost:8000')
        :param timeout: Request timeout in seconds
        """
        
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def make_movie(self, request: MakeMovieRequest) -> MakeMovieResponse:
        """
        Call the /make_movie endpoint.

        :param request: MakeMovieRequest object
        :return: MakeMovieResponse object
        :raises: httpx.HTTPStatusError, ValidationError
        """
        url = "/make_movie"
        try:
            response = self.client.post(url, json=request.model_dump())
            response.raise_for_status()
            return MakeMovieResponse.model_validate(response.json())
        except httpx.HTTPStatusError as exc:
            print(f"HTTP error occurred: {exc.response.status_code} - {exc.response.text}")
            raise
        except ValidationError as exc:
            print(f"Response validation error: {exc}")
            raise

    def close(self):
        """Close the underlying HTTP client."""
        self.client.close()


def main():
    # Parse Args
    parser = argparse.ArgumentParser(description='Editora video maker')
    parser.add_argument('-d', '--directory', required=True, type=str, help='GS path of images')
    parser.add_argument('-t', '--template', type=str, help='Movie template')
    
    url_group = parser.add_mutually_exclusive_group(required=True)
    url_group.add_argument('-l', '--local', action='store_true', help='Route request to local instance')
    url_group.add_argument('-c', '--cloud', action='store_true', help='Route request to cloud service')
    
    args = parser.parse_args()
    LOCAL_HOST='0.0.0.0'
    PORT='8080'
    local_url = f'http://{LOCAL_HOST}:{PORT}'
    cloud_url = 'https://editora-v2-movie-maker-1095143658629.us-central1.run.app'
    
    if args.cloud:
        client = FastAPIClient(base_url=cloud_url)
    elif args.local:
        client = FastAPIClient(base_url=local_url)
    else:
        logger.error("No destination to route request to")
        return
    
    try:
        # Make Movie
        user = Session.UserInfo(
            id='U2'
        )
        project = Session.ProjectInfo(
            id='P5'
        )
        version = Session.VersionInfo(
            id=str(uuid.uuid4())
        )
        session = Session(
            user=user,
            project=project,
            version=version
        )
        
        config = MovieModel.Configuration(
            image_orientation=MovieModel.Configuration.Orientation.Portrait,
            narration=MovieModel.Configuration.Narration(
                enabled=True,
                script='Discover unparalleled luxury on over an acre, featuring designer upgrades, a gourmet kitchen, and lavish amenities like a movie theater and full-court basketball. Explore this exceptional property today',
                captions=False
            ),
            watermark=True,
            end_titles=MovieModel.Configuration.EndTitles(
                main_title='7890 East Grandview Boulevard Mountain View Heights CA 94043',
                sub_title='5 Bed . 4 Bath . 3560 Sqft . 8000 Sqft Lot . $3.4M'
            )
        )
        
        
        ordered_images = [
            "gs://editora-v2-properties/ChIJ3yKdAza7j4AR8iKTRs0ka4I/Images/image1.jpg",
            "gs://editora-v2-properties/ChIJ3yKdAza7j4AR8iKTRs0ka4I/Images/image4.jpg",
            "gs://editora-v2-properties/ChIJ3yKdAza7j4AR8iKTRs0ka4I/Images/image14.jpg",
            "gs://editora-v2-properties/ChIJ3yKdAza7j4AR8iKTRs0ka4I/Images/image17.jpg",
            "gs://editora-v2-properties/ChIJ3yKdAza7j4AR8iKTRs0ka4I/Images/image12.jpg",
            "gs://editora-v2-properties/ChIJ3yKdAza7j4AR8iKTRs0ka4I/Images/image29.jpg",
            "gs://editora-v2-properties/ChIJ3yKdAza7j4AR8iKTRs0ka4I/Images/image9.jpg"
        ]
            
        make_movie_request = MakeMovieRequest(
            request_id=session,
            image_repos=[args.directory],
            # ordered_images=ordered_images,
            template=args.template if args.template else None,
            config=config
        )
        make_movie_response = client.make_movie(request=make_movie_request)
        print(make_movie_response)
        
    except Exception as e:
        logger.error(e)
        
if __name__ == '__main__':
    main()