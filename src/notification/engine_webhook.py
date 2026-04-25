"""
Outbound lifecycle webhooks from kondo-movie → kondos-api.

The receiving end is `POST /internal/videos/:id/callback` on kondos-api,
shared-secret authed via `X-Internal-Token`. Payload shape mirrors the
`EngineWebhookDto` over there: `{ phase, progress, output_url?,
thumbnail_url?, duration_seconds?, error? }`.

Stdlib only — no new dependencies. Sync POST with a short timeout. Fire-
and-forget from the caller's perspective: failures are logged but never
bubble up, because a render that succeeded shouldn't fail the response
just because we couldn't reach kondos-api.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional, TypedDict

from logger import logger


# Same name on both sides of the wire (kondos-api reads as
# `KONDO_MOVIE_WEBHOOK_SECRET`; here it's the value we send).
ENV_TOKEN = "KONDO_WEBHOOK_TOKEN"
DEFAULT_TIMEOUT_SECONDS = 5.0


class WebhookPayload(TypedDict, total=False):
    phase: str  # 'queued' | 'processing' | 'done' | 'failed'
    progress: int  # 0-100
    output_url: str
    thumbnail_url: str
    duration_seconds: int
    error: str


def fire_webhook(
    webhook_url: Optional[str],
    payload: WebhookPayload,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> bool:
    """
    POST a lifecycle update to kondos-api. Returns True on 2xx, False on
    any failure mode (caller never branches on the boolean — it's just
    here for tests). Authentication header sourced from `KONDO_WEBHOOK_TOKEN`;
    when the env var is empty, the call is still attempted (kondos-api
    will reject; that's the explicit signal something is misconfigured).
    """
    if not webhook_url:
        return False

    token = os.getenv(ENV_TOKEN, "")
    body = json.dumps(payload).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Internal-Token"] = token
    else:
        logger.warning(
            f"[engine_webhook] {ENV_TOKEN} not set — kondos-api will reject the webhook. "
            f"Skipping the call rather than burning a round-trip."
        )
        return False

    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            status = getattr(resp, "status", None) or resp.getcode()
            if 200 <= status < 300:
                logger.info(
                    f"[engine_webhook] POST {webhook_url} → {status} (phase={payload.get('phase')})"
                )
                return True
            logger.warning(
                f"[engine_webhook] POST {webhook_url} → {status} (unexpected non-2xx)"
            )
            return False
    except urllib.error.HTTPError as e:
        logger.warning(
            f"[engine_webhook] POST {webhook_url} → HTTP {e.code} {e.reason}"
        )
        return False
    except urllib.error.URLError as e:
        logger.warning(f"[engine_webhook] POST {webhook_url} → URLError: {e.reason}")
        return False
    except (TimeoutError, OSError) as e:
        logger.warning(f"[engine_webhook] POST {webhook_url} → {type(e).__name__}: {e}")
        return False
