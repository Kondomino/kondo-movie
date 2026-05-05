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
from typing import Any, Optional

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
from task_queue.failure_classifier import (
    FailureClassification,
    backoff_for_attempt,
    classify_failure,
)
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
    Worker-side render with classified retry policy (P7).

    Pipeline:
      1. Run MovieActionsHandler.make_movie inside asyncio.to_thread so
         the event loop stays free for heartbeats during the long sync
         work.
      2. If the handler raises OR returns FAILURE: hand the signal to
         classify_failure. If retryable + attempts left → raise
         arq.Retry with backoff (no webhook fired). Else → fire failed
         webhook + return failure dict so the engine.lifecycle reaches
         a terminal state.
      3. On success: fire the done webhook + return the full response.

    Webhook delivery is enqueued as a separate `deliver_webhook` arq
    job (P6). _job_id=f"{render_job_id}:webhook" prevents double-fires.

    On final failure (whether transient-exhausted or fail-fast), arq
    stores the returned dict as the job result so the caller side
    (kondos-api poller) can read terminal state via /jobs/:id/status.
    """
    from arq import Retry

    request = MakeMovieRequestV2.model_validate(request_dict)
    legacy = v2_to_legacy_request(request)

    job_id = ctx.get("job_id") or request.job_id
    job_try: int = int(ctx.get("job_try", 1))
    logger.info(
        f"[VIDEO-WORKER] render started job={job_id} kondo={request.kondo.id} "
        f"try={job_try}"
    )

    # ---- Run the pipeline; capture exception OR failure-state response ----
    caught_exc: Optional[BaseException] = None
    action_response = None
    try:
        action_response = await asyncio.to_thread(
            MovieActionsHandler().make_movie, request=legacy
        )
    except Exception as exc:  # noqa: BLE001
        caught_exc = exc
        logger.warning(
            f"[VIDEO-WORKER] render raised job={job_id} try={job_try}: "
            f"{type(exc).__name__}: {exc}"
        )

    # ---- Decide success vs failure ----
    if caught_exc is None and action_response is not None:
        success = action_response.result.state == ActionStatus.State.SUCCESS
    else:
        success = False

    if success:
        payload = _build_done_payload(action_response)
        await _enqueue_webhook(ctx, request.webhook_url, payload, job_id)
        logger.info(f"[VIDEO-WORKER] render succeeded job={job_id} try={job_try}")
        return action_response.model_dump(mode="json")

    # ---- Failure path: classify, then retry-or-terminal ----
    failure_reason = (
        action_response.result.reason
        if action_response is not None and action_response.result.state != ActionStatus.State.SUCCESS
        else None
    )
    classification = classify_failure(exc=caught_exc, reason=failure_reason)

    # Attempts left? If so, re-raise arq.Retry so the same job_id
    # comes back to the worker after the backoff. The webhook is NOT
    # fired on intermediate retries — only on terminal state.
    if classification.has_attempts_left(job_try):
        defer = backoff_for_attempt(job_try)
        logger.warning(
            f"[VIDEO-WORKER] retry job={job_id} class={classification.failure_class} "
            f"try={job_try}/{classification.max_tries} defer={defer}s"
        )
        raise Retry(defer=defer)

    # Terminal failure: fire failed webhook + return.
    error_text = _build_error_text(caught_exc, action_response)
    payload = {
        "phase": "failed",
        "progress": 100,
        "error": error_text,
    }
    await _enqueue_webhook(ctx, request.webhook_url, payload, job_id)
    logger.error(
        f"[VIDEO-WORKER] render terminal-failed job={job_id} "
        f"class={classification.failure_class} try={job_try}/{classification.max_tries} "
        f"error={error_text}"
    )

    # If the handler returned a clean FAILURE response, return it for
    # forensics; otherwise build a minimal failure dict.
    if action_response is not None:
        return action_response.model_dump(mode="json")
    return {
        "result": {"state": "Failure", "reason": error_text},
        "failure_class": classification.failure_class,
        "tries": job_try,
    }


def _build_done_payload(action_response: Any) -> dict[str, Any]:
    """Webhook payload for a successful render. Falls back to failed-shape
    when the handler reported success but produced no output URL."""
    output_url = action_response.story.movie_path if action_response.story else None
    if not output_url:
        return {
            "phase": "failed",
            "progress": 100,
            "error": "Render reported success but output URL is empty",
        }
    return {"phase": "done", "progress": 100, "output_url": output_url}


def _build_error_text(
    caught_exc: Optional[BaseException], action_response: Any
) -> str:
    if caught_exc is not None:
        return f"{type(caught_exc).__name__}: {caught_exc}"
    if action_response is not None and action_response.result.reason:
        return action_response.result.reason
    return "Engine reported failure (no reason given)"


async def _enqueue_webhook(
    ctx: dict[str, Any],
    webhook_url: str,
    payload: dict[str, Any],
    job_id: str,
) -> None:
    """
    Enqueue durable webhook delivery (P6). _job_id ties it 1:1 to the
    render so duplicate render attempts can't double-fire. Falls back
    to a synchronous best-effort POST when the queue is unreachable.
    """
    payload = {k: v for k, v in payload.items() if v is not None}
    redis = ctx.get("redis")
    if redis is None:
        await _inline_webhook_fallback(webhook_url, payload)
        return
    try:
        await redis.enqueue_job(
            "deliver_webhook",
            webhook_url,
            payload,
            _job_id=f"{job_id}:webhook",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[VIDEO-WORKER] webhook enqueue failed job={job_id}: "
            f"{type(exc).__name__}: {exc} — falling back to inline POST"
        )
        await _inline_webhook_fallback(webhook_url, payload)


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
