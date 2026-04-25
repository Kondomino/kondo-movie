"""
Outbound HTTP client for the kondos-api image-classification cache.

Background: kondo-movie used to write classifications to Firestore. With
the stateless decision (PR 2.6 of the video-tool plan), kondos-api owns
the cache. We hit:

  GET  {KONDOS_API_URL}/internal/classifications/:hash   (read)
  POST {KONDOS_API_URL}/internal/classifications         (write)

Both endpoints are shared-secret authed via `X-Internal-Token` —
matches the kondo-movie → kondos-api webhook auth (same env var,
KONDO_WEBHOOK_TOKEN).

Stdlib only (no new deps). All failures are silent: cache misses behave
like a 404, and a kondos-api outage transparently degrades to "no cache,
just call Vision directly". Caller code never branches on auth/network
errors.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Optional

from logger import logger


ENV_API_URL = "KONDOS_API_URL"
ENV_TOKEN = "KONDO_WEBHOOK_TOKEN"
DEFAULT_TIMEOUT_SECONDS = 5.0


def hash_image_file(path: str) -> str:
    """SHA256 of the file content. Cache key for image classifications."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _base_url_and_token() -> Optional[tuple[str, str]]:
    base = os.getenv(ENV_API_URL, "").rstrip("/")
    token = os.getenv(ENV_TOKEN, "")
    if not base or not token:
        return None
    return base, token


def get_classification(image_hash: str, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> Optional[dict]:
    """
    Returns the cached classification dict on hit, None on miss / error.
    The dict shape mirrors what kondos-api stores — typically
    `{ labels: [...], buckets: {...}, ... }` — opaque to this client.
    """
    creds = _base_url_and_token()
    if not creds:
        return None
    base, token = creds
    url = f"{base}/internal/classifications/{image_hash}"
    req = urllib.request.Request(url, headers={"X-Internal-Token": token}, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            if 200 <= status < 300:
                payload = json.loads(resp.read().decode("utf-8"))
                cached = payload.get("classification")
                if isinstance(cached, dict):
                    logger.debug(f"[classification_cache] HIT {image_hash[:12]}…")
                    return cached
                return None
            return None
    except urllib.error.HTTPError as e:
        if e.code == 404:
            logger.debug(f"[classification_cache] MISS {image_hash[:12]}…")
        else:
            logger.warning(f"[classification_cache] GET {url} → HTTP {e.code} {e.reason}")
        return None
    except urllib.error.URLError as e:
        logger.warning(f"[classification_cache] GET {url} → URLError: {e.reason}")
        return None
    except (TimeoutError, OSError, json.JSONDecodeError) as e:
        logger.warning(f"[classification_cache] GET {url} → {type(e).__name__}: {e}")
        return None


def upsert_classification(
    image_hash: str,
    classification: dict,
    kondo_id: Optional[int] = None,
    source: str = "gcp_vision",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    """Cache write. Returns True on success, False on any failure."""
    creds = _base_url_and_token()
    if not creds:
        return False
    base, token = creds
    url = f"{base}/internal/classifications"
    body: dict = {
        "imageHash": image_hash,
        "classification": classification,
        "source": source,
    }
    if kondo_id is not None:
        body["kondoId"] = kondo_id

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Internal-Token": token},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            if 200 <= status < 300:
                logger.debug(f"[classification_cache] WROTE {image_hash[:12]}…")
                return True
            logger.warning(f"[classification_cache] POST {url} → {status}")
            return False
    except urllib.error.HTTPError as e:
        logger.warning(f"[classification_cache] POST {url} → HTTP {e.code} {e.reason}")
        return False
    except urllib.error.URLError as e:
        logger.warning(f"[classification_cache] POST {url} → URLError: {e.reason}")
        return False
    except (TimeoutError, OSError) as e:
        logger.warning(f"[classification_cache] POST {url} → {type(e).__name__}: {e}")
        return False
