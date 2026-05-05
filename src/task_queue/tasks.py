"""
arq tasks for the kondo-movie worker.

Two surfaces today:

  - `render_movie` (P4) — runs the actual render. Worker-side only;
    the API route enqueues it via `_job_id=request.job_id`. Heavy
    sync work goes through `asyncio.to_thread` so the worker's event
    loop stays free for heartbeats and status pings.

  - `deliver_webhook` (P6) — durable lifecycle webhook delivery.
    Replaces the inline `fire_webhook` call from the render task.
    Retry policy below survives kondos-api outages of up to ~3.5h
    before dead-lettering.

The render task no longer fires the webhook directly — it enqueues a
`deliver_webhook` job with `_job_id=f"{render_job_id}:webhook"` so a
duplicate render attempt doesn't double-fire the webhook.
"""

from __future__ import annotations

import asyncio
from typing import Any

from arq import Retry

from logger import logger
from movie_maker.movie_actions import MovieActionsHandler
from movie_maker.movie_actions_model import (
    MakeMovieRequestV2,
    v2_to_legacy_request,
)
from notification.engine_webhook import (
    WebhookNetworkError,
    post_webhook_once,
)
from task_queue.dead_letter import push_dead_letter
from utils.common_models import ActionStatus


# Backoff schedule between webhook delivery attempts (seconds). Length
# defines max_tries (5). Schedule covers ~3.5h of kondos-api downtime
# before dead-lettering. Indices align with arq's `ctx['job_try']` — 1
# means "this is the first attempt", 2 means "retrying after the first
# failure", etc.
WEBHOOK_RETRY_BACKOFF_SECONDS: list[int] = [10, 60, 300, 1800, 7200]
WEBHOOK_MAX_TRIES: int = len(WEBHOOK_RETRY_BACKOFF_SECONDS)

# HTTP statuses we treat as transient — same retry policy as a network
# error. 408 (request timeout) and 429 (too many requests) are the
# canonical "back off and try again" codes; 5xx is server-side trouble.
_RETRYABLE_HTTP_STATUSES = frozenset({408, 429})


def _is_retryable_status(status_code: int) -> bool:
    return status_code >= 500 or status_code in _RETRYABLE_HTTP_STATUSES


async def render_movie(ctx: dict[str, Any], request_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Worker-side render. Same pipeline as the in-process threadpool path,
    but executed inside the dedicated worker process.

    Heartbeat strategy: the heavy sync MoviePy/ffmpeg work goes through
    `asyncio.to_thread` so the worker's asyncio event loop stays free
    to fire the periodic heartbeat (driven by the on_startup hook in
    worker.py). Without to_thread, a 90s render would block the loop
    and the heartbeat would silently miss its 15s cadence —
    `/readyz` would flap to "stale" mid-render.

    Webhook delivery is now its own arq task (`deliver_webhook`).
    Render success/failure enqueues a delivery job; the render task
    itself no longer touches the network at the end. Failure of the
    render still produces a `phase=failed` webhook so kondos-api can
    flip the row.

    Returns the response as a JSON-serializable dict so arq can store
    it as the job result. The caller (main.py /jobs/:id/status) can
    reconstruct the `MakeMovieResponse` from this dict.
    """
    request = MakeMovieRequestV2.model_validate(request_dict)
    legacy = v2_to_legacy_request(request)

    job_id = ctx.get("job_id") or request.job_id
    logger.info(f"[VIDEO-WORKER] render started job={job_id} kondo={request.kondo.id}")

    action_response = await asyncio.to_thread(
        MovieActionsHandler().make_movie, request=legacy
    )

    success = action_response.result.state == ActionStatus.State.SUCCESS

    if success:
        payload = {
            "phase": "done",
            "progress": 100,
            "output_url": (
                action_response.story.movie_path if action_response.story else None
            ),
        }
        if not payload["output_url"]:
            payload = {
                "phase": "failed",
                "progress": 100,
                "error": "Render reported success but output URL is empty",
            }
    else:
        payload = {
            "phase": "failed",
            "progress": 100,
            "error": (
                action_response.result.reason
                or "Engine reported failure (no reason given)"
            ),
        }
    payload = {k: v for k, v in payload.items() if v is not None}

    # Enqueue the durable webhook delivery. _job_id ties it 1:1 to the
    # render so duplicate render attempts can't double-fire (arq
    # dedups by _job_id). On Redis trouble, fall back to a synchronous
    # best-effort attempt — better one missed retry than nothing.
    redis = ctx.get("redis")
    if redis is not None:
        try:
            await redis.enqueue_job(
                "deliver_webhook",
                request.webhook_url,
                payload,
                _job_id=f"{job_id}:webhook",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[VIDEO-WORKER] webhook enqueue failed job={job_id}: "
                f"{type(exc).__name__}: {exc} — falling back to inline POST"
            )
            await _inline_webhook_fallback(request.webhook_url, payload)
    else:
        # Defensive: ctx['redis'] should always exist in a real arq
        # invocation. Inline fallback keeps the test path working
        # without a live worker pool.
        await _inline_webhook_fallback(request.webhook_url, payload)

    logger.info(
        f"[VIDEO-WORKER] render {'succeeded' if success else 'failed'} job={job_id}"
    )

    return action_response.model_dump(mode="json")


async def _inline_webhook_fallback(webhook_url: str, payload: dict[str, Any]) -> None:
    """
    Best-effort sync POST when the queue is unreachable. Swallows all
    errors — we don't want a stale Redis to fail an otherwise-successful
    render. The kondos-api status poller catches anything we miss.
    """
    try:
        status = await asyncio.to_thread(post_webhook_once, webhook_url, payload)
        logger.info(
            f"[VIDEO-WORKER] inline-fallback webhook → {status} url={webhook_url}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[VIDEO-WORKER] inline-fallback webhook failed url={webhook_url}: "
            f"{type(exc).__name__}: {exc}"
        )


async def deliver_webhook(
    ctx: dict[str, Any],
    webhook_url: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """
    Durable webhook delivery. Sequence per attempt:

      1. POST via post_webhook_once.
      2. 2xx → success, return.
      3. Network error → retry with backoff, dead-letter on max_tries.
      4. HTTP 4xx (not 408/429) → permanent fail, dead-letter, return.
      5. HTTP 5xx / 408 / 429 → retry with backoff, dead-letter on
         max_tries.

    arq's `Retry` exception triggers the requeue with `defer=` seconds.
    `ctx['job_try']` is 1-indexed and reflects the current attempt.

    Returns a small dict for arq's result store. Format documents the
    outcome so an operator can `redis-cli HGETALL` to read it back.
    """
    job_try: int = int(ctx.get("job_try", 1))
    job_id = ctx.get("job_id") or "<no-job-id>"

    is_last_attempt = job_try >= WEBHOOK_MAX_TRIES
    backoff_index = max(job_try - 1, 0)
    backoff_index = min(backoff_index, WEBHOOK_MAX_TRIES - 1)
    next_backoff = WEBHOOK_RETRY_BACKOFF_SECONDS[backoff_index]

    try:
        status_code = await asyncio.to_thread(post_webhook_once, webhook_url, payload)
    except WebhookNetworkError as exc:
        logger.warning(
            f"[VIDEO-WEBHOOK] network error try={job_try}/{WEBHOOK_MAX_TRIES} "
            f"job={job_id} url={webhook_url}: {exc}"
        )
        if is_last_attempt:
            reason = f"network: {exc}"
            await push_dead_letter(
                ctx["redis"],
                webhook_url=webhook_url,
                payload=payload,
                reason=reason,
                attempts=job_try,
                job_id=job_id,
            )
            return {"delivered": False, "reason": reason, "tries": job_try}
        raise Retry(defer=next_backoff)

    if 200 <= status_code < 300:
        logger.info(
            f"[VIDEO-WEBHOOK] delivered status={status_code} try={job_try} "
            f"job={job_id} url={webhook_url}"
        )
        return {"delivered": True, "status": status_code, "tries": job_try}

    retryable = _is_retryable_status(status_code)
    if retryable and not is_last_attempt:
        logger.warning(
            f"[VIDEO-WEBHOOK] http {status_code} try={job_try}/{WEBHOOK_MAX_TRIES} "
            f"job={job_id} — retrying in {next_backoff}s"
        )
        raise Retry(defer=next_backoff)

    # Permanent failure: either a non-retryable 4xx, or we've exhausted
    # retries on a retryable status.
    reason = f"http {status_code}" + (" (max tries exhausted)" if retryable else "")
    await push_dead_letter(
        ctx["redis"],
        webhook_url=webhook_url,
        payload=payload,
        reason=reason,
        attempts=job_try,
        job_id=job_id,
    )
    return {"delivered": False, "reason": reason, "tries": job_try}
