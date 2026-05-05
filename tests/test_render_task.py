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
    import task_queue.tasks as tasks_module

    monkeypatch.setattr(tasks_module, "fire_webhook", lambda *a, **kw: True)

    from task_queue.tasks import render_movie

    result = await render_movie({}, _v2_request_dict())

    assert len(handler_calls) == 1
    legacy = handler_calls[0]
    assert legacy.request_id.version.id == "p5-test-job-1"
    assert legacy.template == "city_beat"
    assert isinstance(result, dict)
    assert result["result"]["state"] == "Success"
    assert result["story"]["movie_path"] == "https://cdn.example.com/out.mp4"


@pytest.mark.asyncio
async def test_render_task_fires_webhook_with_done_payload(monkeypatch):
    """On success the task fires a webhook with phase=done + output_url."""
    from movie_maker import movie_actions

    monkeypatch.setattr(
        movie_actions.MovieActionsHandler,
        "make_movie",
        lambda self, request: _fake_action_response(),
    )

    captured: list[tuple[Any, ...]] = []
    import task_queue.tasks as tasks_module

    def _capture_webhook(url: str, payload: dict, *_: Any, **__: Any) -> bool:
        captured.append((url, payload))
        return True

    monkeypatch.setattr(tasks_module, "fire_webhook", _capture_webhook)

    from task_queue.tasks import render_movie

    await render_movie({}, _v2_request_dict())
    assert len(captured) == 1
    url, payload = captured[0]
    assert url == "https://example.invalid/webhook"
    assert payload["phase"] == "done"
    assert payload["progress"] == 100
    assert payload["output_url"] == "https://cdn.example.com/out.mp4"


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
