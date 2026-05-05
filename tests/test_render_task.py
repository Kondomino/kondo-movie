"""
P4 tests for the worker-side render task.

Two surfaces:
  - `render_movie(ctx, request_dict)` — the arq-callable task in
    `task_queue.tasks`. Translates v2 → legacy, runs the sync pipeline
    via asyncio.to_thread, fires the webhook, returns a JSON-able dict.
  - `/make_movie` route's queue path (`KONDO_MOVIE_USE_QUEUE=true`) —
    enqueues with `_job_id=request.job_id` and awaits the result.

We don't run a real arq worker here (would require Redis + a worker
process). The task is a plain async function — call it directly with
a stubbed `ctx`. The route's enqueue path is tested by patching
`create_pool` to return a mock pool.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Same R2 / config dummies as the other test files.
_R2_DUMMIES = {
    "CLOUDFLARE_R2_KEY_ID": "test-r2-key-id",
    "CLOUDFLARE_R2_ACCESS_KEY": "test-r2-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://test-r2.example.com",
}
for _k, _v in _R2_DUMMIES.items():
    os.environ.setdefault(_k, _v)


def _v2_request_dict() -> dict[str, Any]:
    return {
        "job_id": "p4-test-job-1",
        "agent": {"id": 1, "name": "Test"},
        "kondo": {"id": 1, "address": "Rua X, 0"},
        "media_urls": ["https://cdn.example.com/m1.jpg"],
        "description": "p4-test",
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
            version=Session.VersionInfo(id="p4-test-job-1"),
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


@pytest.mark.asyncio
async def test_render_task_calls_movie_actions(monkeypatch):
    """
    The task must:
      - validate the request_dict back into MakeMovieRequestV2,
      - translate via v2_to_legacy_request,
      - call MovieActionsHandler().make_movie with the legacy request,
      - return a JSON-serialisable dict shape.
    """
    from movie_maker import movie_actions

    handler_calls: list[Any] = []

    def _fake_make_movie(self: Any, request: Any) -> Any:
        handler_calls.append(request)
        return _fake_action_response()

    monkeypatch.setattr(
        movie_actions.MovieActionsHandler, "make_movie", _fake_make_movie
    )
    # No-op the webhook — we don't want network calls in unit tests.
    import task_queue.tasks as tasks_module

    monkeypatch.setattr(tasks_module, "fire_webhook", lambda *a, **kw: True)

    from task_queue.tasks import render_movie

    result = await render_movie({}, _v2_request_dict())

    assert len(handler_calls) == 1, "MovieActionsHandler.make_movie must be invoked once"
    legacy = handler_calls[0]
    # Translation contract: caller's job_id rides on legacy.request_id.version.id.
    assert legacy.request_id.version.id == "p4-test-job-1"
    assert legacy.template == "city_beat"
    # arq stores results via msgpack; dict shape is enough.
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


def test_make_movie_route_enqueues_when_use_queue_flag_on(monkeypatch):
    """
    With KONDO_MOVIE_USE_QUEUE=true, the route must:
      - call arq's create_pool,
      - enqueue 'render_movie' with `_job_id` = caller's request.job_id,
      - await the job's result and return the resulting MakeMovieResponse.

    We patch create_pool to return a mock pool whose enqueue_job returns
    a mock Job with a pre-cooked result. No Redis touched.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("KONDO_MOVIE_USE_QUEUE", "true")

    fake_response_dict = _fake_action_response().model_dump(mode="json")
    job = MagicMock()
    job.result = AsyncMock(return_value=fake_response_dict)
    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=job)
    pool.aclose = AsyncMock(return_value=None)

    with patch("main.create_pool", AsyncMock(return_value=pool)):
        from main import app

        with TestClient(app) as client:
            resp = client.post("/make_movie", json=_v2_request_dict())

    assert resp.status_code == 200, resp.text
    pool.enqueue_job.assert_awaited_once()
    args, kwargs = pool.enqueue_job.call_args
    assert args[0] == "render_movie"
    # Idempotency: the caller-issued UUID is used as arq's _job_id.
    assert kwargs.get("_job_id") == "p4-test-job-1"
    job.result.assert_awaited_once()


def test_make_movie_route_returns_409_when_job_already_queued(monkeypatch):
    """
    arq's `enqueue_job` returns None when a job with the same `_job_id`
    is already queued or running. The route surfaces this as 409 so the
    caller can distinguish it from a fresh enqueue.
    """
    from fastapi.testclient import TestClient

    monkeypatch.setenv("KONDO_MOVIE_USE_QUEUE", "true")

    pool = MagicMock()
    pool.enqueue_job = AsyncMock(return_value=None)  # duplicate job_id
    pool.aclose = AsyncMock(return_value=None)

    with patch("main.create_pool", AsyncMock(return_value=pool)):
        from main import app

        with TestClient(app) as client:
            resp = client.post("/make_movie", json=_v2_request_dict())

    assert resp.status_code == 409
    assert "already in progress" in resp.json().get("detail", "")
