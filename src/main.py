"""
kondo-movie HTTP surface.

The engine is a stateless renderer. Public surface is intentionally small:

    GET    /                       — back-compat health (alias of /healthz)
    GET    /healthz                — cheap liveness (no deps; Fly probe target)
    GET    /readyz                 — readiness (Redis ping + worker heartbeat)
    GET    /api/v1/                — health (kept for parity with proxies)
    POST   /make_movie             — enqueue render; returns 202 + queued
    GET    /jobs/{job_id}/status   — poll lifecycle (kondos-api fallback)
    DELETE /jobs/{job_id}          — cancel (501 until P8)

P5 contract change: /make_movie is fire-and-forget from the route's
perspective. The worker process consumes from the kondo:render arq
queue and drives the lifecycle via webhook back to kondos-api. Callers
get a 202 in <500ms p95 (was 60-90s under the synchronous contract).
"""

from arq import create_pool
from arq.jobs import Job, JobStatus
from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from redis.asyncio import Redis

from logger import logger
from config.config import settings
from movie_maker.movie_actions_model import (
    EngineJobStatusResponse,
    MakeMovieAcceptedResponse,
    MakeMovieRequestV2,
    MakeMovieResponse,
)
from task_queue.connection import get_redis_settings, get_redis_url
from task_queue.heartbeat import (
    HEARTBEAT_STALE_AFTER_SECONDS,
    heartbeat_age_seconds,
    is_heartbeat_stale,
    read_latest_heartbeat,
)


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

@app.post(
    "/make_movie",
    response_model=MakeMovieAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def make_movie(request: MakeMovieRequestV2):
    """
    Enqueue a render onto the worker queue and return 202 immediately.

    The worker (separate Fly machine, see fly.toml `[[processes]]`)
    consumes `kondo:render`, runs the pipeline, and POSTs the lifecycle
    webhook to kondos-api on completion (P6 will move the webhook into
    its own retry-aware queue). Callers should drive the lifecycle via
    that webhook; `GET /jobs/:id/status` is the poll-fallback for when
    the webhook is missed.

    Idempotency: the route passes `_job_id=request.job_id` so a
    duplicate submission of the same kondos-api UUID dedups at the
    arq layer (§2.3 of the plan). When arq reports the job_id is
    already queued/running, this endpoint returns 409.

    Pool creation per-request is wasteful but acceptable at v1 volume.
    A FastAPI lifespan-managed pool is a follow-up (out of P5 scope).
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
            # already queued or running. Surface as 409 so the caller
            # can distinguish from a fresh enqueue.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Render job_id={request.job_id} already in progress",
            )
    finally:
        await pool.aclose()

    logger.info(f"[VIDEO-API] enqueued render job_id={request.job_id} kondo={request.kondo.id}")
    return MakeMovieAcceptedResponse(job_id=request.job_id, status="queued")


# ---- Job lifecycle ----

# Maps arq's internal job state to our public lifecycle phase.
# arq's JobStatus enum values: deferred, queued, in_progress, complete, not_found.
_ARQ_STATUS_TO_PHASE: dict[JobStatus, str] = {
    JobStatus.deferred: "queued",
    JobStatus.queued: "queued",
    JobStatus.in_progress: "processing",
    # `complete` is split into done/failed by inspecting the result —
    # see _job_status_payload below.
    JobStatus.not_found: "failed",
}


async def _job_status_payload(pool, job_id: str) -> EngineJobStatusResponse:
    """
    Build the public status shape from arq's job state. Reads the result
    when the job is complete to derive done vs failed and surface the
    output URL / error.
    """
    job = Job(job_id=job_id, redis=pool)
    arq_status = await job.status()

    if arq_status == JobStatus.not_found:
        # Job either never existed or was evicted past keep_result.
        # 404 lets the caller (kondos-api poller) decide whether to
        # mark the row failed.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"job_id={job_id} not found",
        )

    if arq_status != JobStatus.complete:
        return EngineJobStatusResponse(
            job_id=job_id,
            phase=_ARQ_STATUS_TO_PHASE[arq_status],
            progress=0 if arq_status in (JobStatus.deferred, JobStatus.queued) else 50,
        )

    # complete — inspect the result. arq's result_info() returns a
    # JobResult with `success` (bool) and `result` (the task return).
    result_info = await job.result_info()
    if result_info is None or not result_info.success:
        return EngineJobStatusResponse(
            job_id=job_id,
            phase="failed",
            progress=100,
            error=(
                str(result_info.result) if result_info is not None else "Job result unavailable"
            ),
        )

    # The render task returns a MakeMovieResponse dict. Reconstruct
    # to read story.movie_path; failed-render-with-success-job (no
    # output URL) is rare but handled by validating presence.
    try:
        full = MakeMovieResponse.model_validate(result_info.result)
    except Exception as exc:  # noqa: BLE001
        return EngineJobStatusResponse(
            job_id=job_id,
            phase="failed",
            progress=100,
            error=f"Invalid worker result shape: {type(exc).__name__}",
        )

    output_url = full.story.movie_path if full.story else None
    return EngineJobStatusResponse(
        job_id=job_id,
        phase="done" if output_url else "failed",
        progress=100,
        output_url=output_url,
        error=None if output_url else "Render completed but output URL is empty",
    )


@app.get("/jobs/{job_id}/status", response_model=EngineJobStatusResponse)
async def get_job_status(job_id: str):
    """
    Poll-fallback consumed by kondos-api's VideoStatusPollerService
    when a webhook is missed. Reads arq's job state directly from
    Redis — no caching, no extra DB hop.
    """
    pool = await create_pool(get_redis_settings())
    try:
        return await _job_status_payload(pool, job_id)
    finally:
        await pool.aclose()


@app.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    """
    P8 will implement real cancellation via arq's abort_job. Until
    then this stays a 501 so kondos-api's cancel UX surfaces a clean
    "not implemented" rather than a silent success.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            f"Job cancellation lands in P8 (job_id={job_id}). "
            "Operator-driven retry/cancel UI ships with that phase."
        ),
    )
