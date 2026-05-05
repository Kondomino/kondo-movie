"""
kondo-movie HTTP surface.

The engine is a stateless renderer. Public surface is intentionally small:

    GET  /                       — back-compat health (alias of /healthz)
    GET  /healthz                — cheap liveness (no deps; Fly probe target)
    GET  /readyz                 — readiness (Redis ping + worker heartbeat)
    GET  /api/v1/                — health (kept for parity with proxies)
    POST /make_movie             — render endpoint (v2 proxied-identity contract)
    GET  /jobs/{job_id}/status   — polling fallback (501 until arq lands)
    DELETE /jobs/{job_id}        — cancel (501 until arq lands)

Everything else (Editora-era account/property/legacy-video routes) was
removed in PR k4 alongside the Firestore purge.
"""

import os

from arq import create_pool
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from redis.asyncio import Redis

from logger import logger
from config.config import settings
from movie_maker.movie_actions import MovieActionsHandler
from movie_maker.movie_actions_model import (
    MakeMovieRequestV2,
    MakeMovieResponse,
    v2_to_legacy_request,
)
from utils.common_models import ActionStatus
from notification.engine_webhook import fire_webhook
from task_queue.connection import get_redis_settings, get_redis_url
from task_queue.heartbeat import (
    HEARTBEAT_STALE_AFTER_SECONDS,
    heartbeat_age_seconds,
    is_heartbeat_stale,
    read_latest_heartbeat,
)


def _use_queue() -> bool:
    """
    Feature flag for the P4 worker path. Default false — the route runs
    the render in-process via run_in_threadpool (P2 behavior). Flip to
    true via `fly secrets set KONDO_MOVIE_USE_QUEUE=true` once the
    worker process is deployed and `/readyz` reports `worker: ok`.
    Acts as the rollback switch if the queue path misbehaves.
    """
    return os.getenv("KONDO_MOVIE_USE_QUEUE", "false").lower() == "true"


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.Authentication.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Exception handlers (keep responses JSON-shaped for kondos-api) ----

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.exception(exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc)},
    )


@app.exception_handler(ValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: ValidationError):
    logger.exception(exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc)},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.exception(exc)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.exception(exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )


# ---- Health & readiness ----
#
# Two-tier model (P3 of the reliability plan):
#   /healthz — liveness. Process is up, FastAPI is serving. Cheap: no
#              Redis, no DB, no external calls. Fly's `[checks.health]`
#              probe targets this so a slow Redis can't flap the
#              machine state.
#   /readyz  — readiness. Pings Redis and reads the latest worker
#              heartbeat. 503 when degraded so ops dashboards / external
#              uptime checks (UptimeRobot etc) see real state.
# `/` and `/api/v1/` stay around as back-compat aliases of /healthz —
# anything probing the old endpoints keeps working.


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(response: Response):
    """
    Readiness — pings Redis and inspects the latest worker heartbeat.

    Today (P3 baseline) there are no workers writing heartbeats yet;
    the worker process arrives in P4. So the expected production state
    immediately after this PR is `degraded` with `worker: "no-heartbeat"`.
    That's intentional and surfaced in the body so it doesn't get
    confused with a real outage. Once P4 ships, healthy workers will
    flip the readiness probe to `ok`.
    """
    redis_ok = False
    redis_error: str | None = None
    redis: Redis | None = None
    try:
        redis = Redis.from_url(
            get_redis_url(), socket_timeout=2.0, socket_connect_timeout=2.0
        )
        redis_ok = bool(await redis.ping())
    except Exception as exc:  # noqa: BLE001
        redis_error = f"{type(exc).__name__}: {exc}"
    try:
        latest = await read_latest_heartbeat(redis) if redis_ok and redis else None
    except Exception as exc:  # noqa: BLE001
        latest = None
        redis_error = redis_error or f"heartbeat-read: {type(exc).__name__}: {exc}"
    finally:
        if redis is not None:
            try:
                await redis.aclose()
            except Exception:  # noqa: BLE001
                pass

    age = heartbeat_age_seconds(latest)
    stale = is_heartbeat_stale(latest)

    healthy = redis_ok and not stale
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ok" if healthy else "degraded",
        "redis": redis_ok,
        "redis_error": redis_error,
        "worker_heartbeat_age_seconds": age,
        "worker_heartbeat_stale_after_seconds": HEARTBEAT_STALE_AFTER_SECONDS,
        "worker": "ok" if (latest is not None and not stale) else "no-heartbeat",
    }


@app.get("/")
async def read_root():
    return {"status": "ok", "service": "kondo-movie"}


v1_router = APIRouter(prefix="/api/v1")


@v1_router.get("/")
async def read_root_v1():
    return {"status": "ok", "service": "kondo-movie", "api": "v1"}


app.include_router(v1_router)


# ---- Render ----

@app.post("/make_movie", response_model=MakeMovieResponse)
async def make_movie(request: MakeMovieRequestV2, response: Response):
    """
    v2 proxied-identity render endpoint. Translates to the engine's
    internal request shape and runs through the stateless handler. Fires
    a lifecycle webhook back to kondos-api on completion (best-effort).

    Two execution paths, gated on KONDO_MOVIE_USE_QUEUE:

    - default (false): in-process via run_in_threadpool (P2 behavior).
      The blocking sync render runs in the threadpool so the asyncio
      loop stays responsive for `/healthz` etc.

    - true: enqueue onto arq, await the worker's result. Worker process
      lives on a separate Fly machine (per fly.toml `[[processes]]`).
      Same external response — caller still gets the full
      `MakeMovieResponse` synchronously. P5 will flip the route to
      return 202 immediately and let the webhook drive the lifecycle.

    Idempotency: the queue path passes `_job_id=request.job_id` so a
    duplicate submission of the same kondos-api UUID dedups at the
    arq layer (§2.3 of the plan).
    """
    if _use_queue():
        return await _make_movie_via_queue(request, response)
    return await _make_movie_inline(request, response)


async def _make_movie_inline(
    request: MakeMovieRequestV2, response: Response
) -> MakeMovieResponse:
    """In-process P2 path. Render + webhook go through the threadpool."""
    legacy_request = v2_to_legacy_request(request)
    action_response = await run_in_threadpool(
        MovieActionsHandler().make_movie, request=legacy_request
    )
    success = action_response.result.state == ActionStatus.State.SUCCESS
    if not success:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    payload = _webhook_payload_from_response(action_response, success)
    await run_in_threadpool(fire_webhook, request.webhook_url, payload)
    return action_response


async def _make_movie_via_queue(
    request: MakeMovieRequestV2, response: Response
) -> MakeMovieResponse:
    """
    Queue path. Enqueues with the caller's UUID as the arq job_id and
    waits for the worker to finish.

    Pool creation per-request: wasteful but acceptable at v1 volume.
    P5 refactors to FastAPI lifespan-managed pool when we re-shape
    the route around 202 + webhook.

    Job timeout matches the worker's `job_timeout=600s` so a stuck
    render bubbles up as a clean failure rather than hanging the
    request indefinitely.
    """
    pool = await create_pool(get_redis_settings())
    try:
        job = await pool.enqueue_job(
            "render_movie",
            request.model_dump(mode="json"),
            _job_id=request.job_id,
        )
        if job is None:
            # arq returns None when a job with the same _job_id is
            # already queued or running. Idempotent retry — surface
            # via 409 so the caller knows it's not a fresh submission.
            response.status_code = status.HTTP_409_CONFLICT
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Render job_id={request.job_id} already in progress",
            )
        result_dict = await job.result(timeout=600)
    finally:
        await pool.aclose()

    action_response = MakeMovieResponse.model_validate(result_dict)
    success = action_response.result.state == ActionStatus.State.SUCCESS
    if not success:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    return action_response


def _webhook_payload_from_response(
    action_response: MakeMovieResponse, success: bool
) -> dict:
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
    return {k: v for k, v in payload.items() if v is not None}


# ---- Job lifecycle (501 stubs — arq integration pending) ----

@app.get("/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    raise HTTPException(
        status_code=501,
        detail=(
            f"Job-status polling is not yet implemented (job_id={job_id}). "
            "This endpoint will land with the arq worker integration. Until then, "
            "/make_movie remains synchronous and returns the final result inline."
        ),
    )


@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    raise HTTPException(
        status_code=501,
        detail=(
            f"Job cancellation is not yet implemented (job_id={job_id}). "
            "This endpoint will land with the arq worker integration."
        ),
    )
