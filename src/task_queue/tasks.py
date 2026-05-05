"""
arq tasks for the kondo-movie worker.

P4 of the reliability plan: the actual render is now a worker-side
arq job, dequeued by the worker process, executed inside
`asyncio.to_thread` so the event loop stays free for heartbeats and
status pings.

The route side (main.py) enqueues with `_job_id=request.job_id` so the
caller-issued UUID drives idempotency (§2.3 of the plan). Today the
route still awaits the result inline — same external contract as P2.
P5 flips the route to return 202 immediately; this task stays
unchanged because the unit of work is identical.
"""

from __future__ import annotations

import asyncio
from typing import Any

from logger import logger
from movie_maker.movie_actions import MovieActionsHandler
from movie_maker.movie_actions_model import (
    MakeMovieRequestV2,
    v2_to_legacy_request,
)
from notification.engine_webhook import fire_webhook
from utils.common_models import ActionStatus


async def render_movie(ctx: dict[str, Any], request_dict: dict[str, Any]) -> dict[str, Any]:
    """
    Worker-side render. Same pipeline as the in-process threadpool path,
    but executed inside the dedicated worker process.

    Heartbeat strategy: the heavy sync MoviePy/ffmpeg work goes through
    `asyncio.to_thread` so the worker's asyncio event loop stays free
    to fire the periodic heartbeat (driven by the on_startup hook in
    worker.py, max_jobs=1 doesn't apply to it). Without to_thread, a
    90s render would block the loop and the heartbeat would silently
    miss its 15s cadence — `/readyz` would flap to "stale" mid-render.

    Webhook delivery still happens inline at the end (same fire-and-
    forget shape as P2). P6 of the plan extracts it into its own arq
    queue with retry + dead-letter; until then we accept the same
    delivery characteristics we have today.

    Returns the response as a JSON-serializable dict so arq can store
    it as the job result. The caller (main.py) reconstructs the
    `MakeMovieResponse` from this dict.
    """
    request = MakeMovieRequestV2.model_validate(request_dict)
    legacy = v2_to_legacy_request(request)

    job_id = ctx.get("job_id") or request.job_id
    logger.info(f"[VIDEO-WORKER] render started job={job_id} kondo={request.kondo.id}")

    # Run the blocking render off the event loop so the heartbeat keeps
    # firing. asyncio.to_thread is Python 3.9+ — safe on our 3.12 base.
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

    # Webhook still inline; P6 moves it to its own retry-aware queue.
    await asyncio.to_thread(fire_webhook, request.webhook_url, payload)

    logger.info(
        f"[VIDEO-WORKER] render {'succeeded' if success else 'failed'} job={job_id}"
    )

    # arq serializes the return value via msgpack; pydantic's
    # `model_dump(mode='json')` produces a fully-compatible dict.
    return action_response.model_dump(mode="json")
