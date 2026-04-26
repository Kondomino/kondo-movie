"""
Stateless image-fetch helpers used by `movie_actions._fetch_images`.

Lives in its own module so tests can import without dragging in the
DB/Firestore side effects that `movie_actions` triggers transitively
(via `utils.session_utils`). Pure I/O + URL helpers — no engine state.
"""

from pathlib import Path
from urllib.parse import urlparse

import requests


_HTTP_DOWNLOAD_TIMEOUT_SECONDS = 60
_HTTP_DOWNLOAD_CHUNK_SIZE = 1 << 16  # 64 KiB


def download_http_image(url: str, dest_file: str) -> None:
    """
    Stream an http(s) image to disk. Used when the upstream (kondos-api)
    sends public/signed URLs from R2 / DO Spaces / other S3-compatible
    storage. Raises ValueError on non-2xx so the caller surfaces a clean
    failure reason in the lifecycle webhook.
    """
    response = requests.get(url, stream=True, timeout=_HTTP_DOWNLOAD_TIMEOUT_SECONDS)
    if response.status_code >= 400:
        raise ValueError(
            f"Failed to download image: HTTP {response.status_code} for {url}"
        )
    with open(dest_file, "wb") as fh:
        for chunk in response.iter_content(chunk_size=_HTTP_DOWNLOAD_CHUNK_SIZE):
            if chunk:
                fh.write(chunk)


def suffix_from_url(url: str) -> str:
    """
    Pick a file suffix from an http(s) URL — strip query/fragment first
    so signed-URL params (?X-Amz-...) don't pollute the filename.
    Defaults to `.jpg` when the URL doesn't carry a recognizable extension.
    """
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix
    return suffix if suffix else ".jpg"


def is_http_url(url: str) -> bool:
    """True for http:// or https:// URLs; False for gs://, s3://, local paths, etc."""
    return urlparse(url).scheme.lower() in ("http", "https")
