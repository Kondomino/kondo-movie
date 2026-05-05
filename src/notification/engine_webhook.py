"""
Outbound lifecycle webhooks from kondo-movie → kondos-api.

The receiving end is `POST /internal/videos/:id/callback` on kondos-api,
shared-secret authed via `X-Internal-Token`. Payload shape mirrors the
`EngineWebhookDto` over there: `{ phase, progress, output_url?,
thumbnail_url?, duration_seconds?, error? }`.

Two surfaces:

  - `fire_webhook(url, payload) -> bool` — legacy fire-and-forget shape.
    Returns True on 2xx, False otherwise. All errors swallowed. Used
    only by tests + any back-compat caller; production goes through
    `post_webhook_once` + the durable arq task in P6+.

  - `post_webhook_once(url, payload) -> int` — single-attempt
    deliverer that returns the HTTP status code on response and
    raises `WebhookNetworkError` on transport failure. Used by the
    `deliver_webhook` arq task to decide retry vs dead-letter.

Stdlib only — no new dependencies. Sync POST with a short timeout.
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


class WebhookNetworkError(Exception):
    """
    Transport-layer failure (timeout, DNS, connection refused, etc.).
    Distinct from an HTTP response with a 4xx/5xx code so the arq task
    can apply different retry policy: network errors always retry until
    max_tries, HTTP responses dispatch on the code.
    """

    def __init__(self, cause: BaseException):
        self.cause = cause
        super().__init__(f"{type(cause).__name__}: {cause}")


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


def post_webhook_once(
    webhook_url: str,
    payload: WebhookPayload,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> int:
    """
    Single-attempt POST that returns the HTTP status code or raises
    `WebhookNetworkError` on transport failure.

    Distinguishes 4xx/5xx responses (caller decides retry policy by
    status code) from network failures (always retry).

    Used by the `deliver_webhook` arq task — see task_queue.tasks. Not
    intended for direct use by route handlers.
    """
    if not webhook_url:
        raise ValueError("webhook_url is required")

    token = os.getenv(ENV_TOKEN, "")
    body = json.dumps(payload).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Internal-Token"] = token

    request = urllib.request.Request(
        webhook_url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        # urllib raises HTTPError for non-2xx responses — catch it and
        # surface the code so the caller can decide retry policy. Other
        # errors (URLError, TimeoutError, OSError) are transport-layer
        # and bubble as WebhookNetworkError.
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return getattr(resp, "status", None) or resp.getcode()
    except urllib.error.HTTPError as e:
        # 4xx/5xx — return the status code, no exception. Caller
        # branches on code.
        return e.code
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise WebhookNetworkError(e) from e
