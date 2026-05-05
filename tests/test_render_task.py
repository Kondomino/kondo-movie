"""
P5 contract tests:
  - the worker-side render task still does what it did in P4 (translate
    request, run pipeline, fire webhook, return result dict)
  - the public /make_movie route returns 202 + the queued-shape body
    immediately, with no inline render and no waiting on the worker
  - duplicate job_ids surface as 409 (idempotency contract)

We don't run a real arq worker here — the task is a plain async fn,
called directly with a stub ctx. The route is exercised via TestClient
with `arq.create_pool` patched so no Redis is touched.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Same R2 / config dummies as the other test files — imports of
# storage_manager validate at module load time.
_R2_DUMMIES = {
    "CLOUDFLARE_R2_KEY_ID": "test-r2-key-id",
    "CLOUDFLARE_R2_ACCESS_KEY": "test-r2-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://test-r2.example.com",
}
for _k, _v in _R2_DUMMIES.items():
    os.environ.setdefault(_k, _v)


def _v2_request_dict() -> dict[str, Any]:
    return {
        "job_id": "p5-test-job-1",
        "agent": {"id": 1, "name": "Test"},
        "kondo": {"id": 1, "address": "Rua X, 0"},
        "media_urls": ["https://cdn.example.com/m1.jpg"],
        "description": "p5-test",
        "edl_id": "city_beat",
        "voice_id": None,
        "music_url": None,
        "webhook_url": "https://example.invalid/webhook",
        "capabilities": {
            "duration_max_seconds": 30,
            "images_max": 10,
            "captions_enabled": False,
        },
    }


def _fake_action_response() -> Any:
    """Build a real, schema-valid MakeMovieResponse for the success path."""
    from movie_maker.movie_actions_model import MakeMovieResponse, Story
    from movie_maker.movie_model import MovieModel
    from utils.common_models import ActionStatus, Session

    now = datetime.now(timezone.utc)
    return MakeMovieResponse(
        request_id=Session(
            user=Session.UserInfo(id="1"),
            project=Session.ProjectInfo(id="1"),
            version=Session.VersionInfo(id="p5-test-job-1"),
        ),
        result=ActionStatus(state=ActionStatus.State.SUCCESS),
        created=now,
        last_updated=now,
        story=Story(
            template="city_beat",
            config=MovieModel.Configuration(),
            used_images=["https://cdn.example.com/m1.jpg"],
            movie_path="https://cdn.example.com/out.mp4",
        ),
    )


# ---- Worker task ----

def _ctx_with_mocked_redis() -> dict[str, Any]:
    """Stub arq context with an enqueue_job mock so the render task can
    enqueue the webhook delivery without a real Redis pool."""
    redis = MagicMock()
    redis.enqueue_job = AsyncMock(return_value=MagicMock())
    return {"redis": redis, "job_id": "p5-test-job-1"}


@pytest.mark.asyncio
async def test_render_task_calls_movie_actions(monkeypatch):
    """
    Task contract: validate request_dict, translate v2→legacy, invoke
    MovieActionsHandler.make_movie, return JSON-serialisable dict.
    """
    from movie_maker import movie_actions

    handler_calls: list[Any] = []

    def _fake_make_movie(self: Any, request: Any) -> Any:
        handler_calls.append(request)
        return _fake_action_response()

    monkeypatch.setattr(
        movie_actions.MovieActionsHandler, "make_movie", _fake_make_movie
    )

    from task_queue.tasks import render_movie

    result = await render_movie(_ctx_with_mocked_redis(), _v2_request_dict())

    assert len(handler_calls) == 1
    legacy = handler_calls[0]
    assert legacy.request_id.version.id == "p5-test-job-1"
    assert legacy.template == "city_beat"
    assert isinstance(result, dict)
    assert result["result"]["state"] == "Success"
    assert result["story"]["movie_path"] == "https://cdn.example.com/out.mp4"


@pytest.mark.asyncio
async def test_oom_does_not_retry(monkeypatch):
    """
    P7: OOM is non-retryable. The render task must NOT raise arq.Retry
    on a MemoryError; it fires the failed webhook and returns terminal.
    """
    from arq import Retry
    from movie_maker import movie_actions

    def _oom(self: Any, request: Any) -> Any:
        raise MemoryError("simulated OOM")

    monkeypatch.setattr(movie_actions.MovieActionsHandler, "make_movie", _oom)

    ctx = _ctx_with_mocked_redis()
    ctx["job_try"] = 1

    from task_queue.tasks import render_movie

    # No Retry raised — the task returns a failure dict.
    result = await render_movie(ctx, _v2_request_dict())
    assert isinstance(result, dict)
    assert result["result"]["state"] == "Failure"
    assert result["failure_class"] == "oom"

    # And the failed webhook got enqueued.
    ctx["redis"].enqueue_job.assert_awaited_once()
    args, _ = ctx["redis"].enqueue_job.call_args
    assert args[0] == "deliver_webhook"
    assert args[2]["phase"] == "failed"


@pytest.mark.asyncio
async def test_r2_5xx_retries_with_backoff(monkeypatch):
    """
    P7: R2 503 is retryable up to 5 attempts. On try=1 the task must
    raise arq.Retry rather than fire a webhook.
    """
    from arq import Retry
    from movie_maker import movie_actions

    class _FakeClientError(Exception):
        pass

    def _r2_503(self: Any, request: Any) -> Any:
        err = _FakeClientError("R2 upload failed")
        err.response = {"ResponseMetadata": {"HTTPStatusCode": 503}}
        raise err

    monkeypatch.setattr(movie_actions.MovieActionsHandler, "make_movie", _r2_503)

    ctx = _ctx_with_mocked_redis()
    ctx["job_try"] = 1

    from task_queue.tasks import render_movie

    with pytest.raises(Retry):
        await render_movie(ctx, _v2_request_dict())

    # The webhook is NOT fired on intermediate retries — only on
    # terminal state. This is the contract that lets the engine
    # complete its retry loop without spamming kondos-api with
    # transient phase=failed callbacks.
    ctx["redis"].enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_r2_5xx_terminal_after_max_tries(monkeypatch):
    """Last attempt of a retryable failure dead-letters via failed webhook."""
    from movie_maker import movie_actions

    class _FakeClientError(Exception):
        pass

    def _r2_503(self: Any, request: Any) -> Any:
        err = _FakeClientError("R2 upload failed")
        err.response = {"ResponseMetadata": {"HTTPStatusCode": 503}}
        raise err

    monkeypatch.setattr(movie_actions.MovieActionsHandler, "make_movie", _r2_503)

    ctx = _ctx_with_mocked_redis()
    ctx["job_try"] = 5  # max_tries for r2_upload

    from task_queue.tasks import render_movie

    result = await render_movie(ctx, _v2_request_dict())
    assert result["failure_class"] == "r2_upload"
    ctx["redis"].enqueue_job.assert_awaited_once()
    args, _ = ctx["redis"].enqueue_job.call_args
    assert args[2]["phase"] == "failed"


@pytest.mark.asyncio
async def test_render_task_enqueues_deliver_webhook_on_done(monkeypatch):
    """
    P6 contract: the render task no longer fires the webhook inline. It
    enqueues a `deliver_webhook` arq job with `_job_id=<render-id>:webhook`
    so duplicate render attempts can't double-fire.
    """
    from movie_maker import movie_actions

    monkeypatch.setattr(
        movie_actions.MovieActionsHandler,
        "make_movie",
        lambda self, request: _fake_action_response(),
    )

    ctx = _ctx_with_mocked_redis()

    from task_queue.tasks import render_movie

    await render_movie(ctx, _v2_request_dict())

    ctx["redis"].enqueue_job.assert_awaited_once()
    args, kwargs = ctx["redis"].enqueue_job.call_args
    assert args[0] == "deliver_webhook"
    # args[1] is webhook_url, args[2] is the payload dict
    assert args[1] == "https://example.invalid/webhook"
    payload = args[2]
    assert payload["phase"] == "done"
    assert payload["progress"] == 100
    assert payload["output_url"] == "https://cdn.example.com/out.mp4"
    # Idempotency tag: render's job_id + ':webhook' suffix
    assert kwargs.get("_job_id") == "p5-test-job-1:webhook"


# ---- /make_movie route — P5 contract ----

def test_make_movie_returns_202_with_queued_shape():
    """
    The route MUST return immediately with HTTP 202 and the
    `MakeMovieAcceptedResponse` shape — no waiting on the worker, no
    full render result inline. This is the P5 contract change.
    """
    from fastapi.testclient import TestClient

    job = MagicMock()
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=job)
    pool.aclose = AsyncMock(return_value=None)

    with patch("main.create_pool", AsyncMock(return_value=pool)):
        from main import app

        with TestClient(app) as client:
            resp = client.post("/make_movie", json=_v2_request_dict())

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == "p5-test-job-1"
    assert body["status"] == "queued"
    pool.enqueue_job.assert_awaited_once()
    args, kwargs = pool.enqueue_job.call_args
    assert args[0] == "render_movie"
    # Idempotency: caller-issued UUID drives arq's _job_id.
    assert kwargs.get("_job_id") == "p5-test-job-1"
    # 202 + queued shape proves the route doesn't wait on the worker —
    # the old contract returned the full MakeMovieResponse with story
    # populated, which is incompatible with this body.


def test_make_movie_route_returns_409_when_job_already_queued():
    """
    arq's enqueue_job returns None when a job with the same `_job_id`
    is already queued or running. The route surfaces this as 409.
    """
    from fastapi.testclient import TestClient

    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)
    pool.aclose = AsyncMock(return_value=None)

    with patch("main.create_pool", AsyncMock(return_value=pool)):
        from main import app

        with TestClient(app) as client:
            resp = client.post("/make_movie", json=_v2_request_dict())

    assert resp.status_code == 409
    assert "already in progress" in resp.json().get("detail", "")
