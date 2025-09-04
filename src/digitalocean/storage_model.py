from pathlib import Path
from typing import Optional
from pydantic import BaseModel

class CloudPath(BaseModel):
    """
    Digital Ocean Spaces path model - compatible with existing GCP CloudPath interface
    """
    bucket_id: str
    path: Path
    
    def full_path(self) -> str:
        """
        Generate full Digital Ocean Spaces path
        Format: s3://bucket-name/path/to/file
        """
        return f"s3://{self.bucket_id}/{self.path}"
    
    def cdn_url(self, cdn_endpoint: str) -> str:
        """
        Generate CDN URL for faster access
        Format: https://cdn-endpoint/path/to/file
        """
        return f"{cdn_endpoint.rstrip('/')}/{self.path}"
    
    def origin_url(self, origin_endpoint: str) -> str:
        """
        Generate origin URL for direct access
        Format: https://bucket-name.origin-endpoint/path/to/file
        """
        # Extract base endpoint from full endpoint URL
        if '://' in origin_endpoint:
            protocol, endpoint = origin_endpoint.split('://', 1)
            return f"{protocol}://{self.bucket_id}.{endpoint}/{self.path}"
        else:
            return f"https://{self.bucket_id}.{origin_endpoint}/{self.path}"
