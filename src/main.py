"""
kondo-movie HTTP surface.

The engine is a stateless renderer. Public surface is intentionally small:

    GET  /                       — health
    GET  /api/v1/                — health (kept for parity with proxies)
    POST /make_movie             — render endpoint (v2 proxied-identity contract)
    GET  /jobs/{job_id}/status   — polling fallback (501 until arq lands)
    DELETE /jobs/{job_id}        — cancel (501 until arq lands)

Everything else (Editora-era account/property/legacy-video routes) was
removed in PR k4 alongside the Firestore purge.
"""

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

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


# ---- Health ----

@app.get("/")
async def read_root():
    return {"message": "kondo-movie · stateless renderer · ok"}


v1_router = APIRouter(prefix="/api/v1")


@v1_router.get("/")
async def read_root_v1():
    return {"message": "kondo-movie · v1 · ok"}


app.include_router(v1_router)


# ---- Render ----

@app.post("/make_movie", response_model=MakeMovieResponse)
async def make_movie(request: MakeMovieRequestV2, response: Response):
    """
    v2 proxied-identity render endpoint. Translates to the engine's
    internal request shape and runs through the stateless handler. Fires
    a lifecycle webhook back to kondos-api on completion (best-effort).
    """
    legacy_request = v2_to_legacy_request(request)
    action_response = MovieActionsHandler().make_movie(request=legacy_request)
    success = action_response.result.state == ActionStatus.State.SUCCESS
    if not success:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR

    if success:
        payload = {
            "phase": "done",
            "progress": 100,
            "output_url": action_response.story.movie_path if action_response.story else None,
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
            "error": action_response.result.reason or "Engine reported failure (no reason given)",
        }
    payload = {k: v for k, v in payload.items() if v is not None}
    fire_webhook(request.webhook_url, payload)

    return action_response


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
