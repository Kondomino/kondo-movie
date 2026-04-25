from pathlib import Path
from typing import Optional
from pydantic import BaseModel


class CloudPath(BaseModel):
    """
    Cloudflare R2 path model — compatible with the existing GCP/DO CloudPath
    interface so the same internal callers work regardless of provider.
    """

    bucket_id: str
    path: Path

    def full_path(self) -> str:
        """
        Generate full R2 path.
        Format: s3://bucket-name/path/to/file
        """
        return f"s3://{self.bucket_id}/{self.path}"

    def public_url(self, public_url_prefix: str) -> str:
        """
        Generate public URL for direct access (e.g. through a custom domain
        bound to the R2 bucket, or `pub-<id>.r2.dev`).
        Format: <public_url_prefix>/path/to/file
        """
        return f"{public_url_prefix.rstrip('/')}/{self.path}"

    def origin_url(self, endpoint: str) -> str:
        """
        Generate S3-style virtual-hosted URL via the R2 endpoint.
        Format: https://bucket.<endpoint>/path/to/file
        """
        if "://" in endpoint:
            protocol, host = endpoint.split("://", 1)
            return f"{protocol}://{self.bucket_id}.{host}/{self.path}"
        return f"https://{self.bucket_id}.{endpoint}/{self.path}"
