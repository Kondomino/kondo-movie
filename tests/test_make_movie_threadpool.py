"""
P2 of the video-render-reliability plan: prove that `/make_movie` no
longer blocks the asyncio event loop during a render. Without
`run_in_threadpool` wrapping the sync render and webhook calls, a
real /healthz probe would queue behind the 60-90s blocking work,
Fly would mark the machine unhealthy, and the render would die.

Strategy:
- Monkeypatch `MovieActionsHandler.make_movie` to a `time.sleep(2)`
  stub that simulates the long sync render without doing real work.
- Monkeypatch `fire_webhook` to a no-op (we don't want network calls).
- Drive `/make_movie` and `/` concurrently. With the threadpool wrap
  in place, `/` should complete in well under the 2s sleep duration.
- Without the wrap, `/` would queue behind the blocking call and only
  return after ~2s. The threshold below catches the regression.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.fixture
def app_with_stubbed_render(monkeypatch: pytest.MonkeyPatch):
    """
    Yield a FastAPI app whose render path is replaced by a 2-second sync
    sleep + a synthetic success response, and whose webhook is a no-op.
    """
    # Import lazily so monkeypatch.setattr can target the live class.
    from main import app  # noqa: WPS433
    from movie_maker import movie_actions  # noqa: WPS433

    # 1) Stub the heavy sync render. The signature must match
    #    MovieActionsHandler.make_movie(self, request=...). We build a real
    #    `MakeMovieResponse` so FastAPI's response_model validation passes.
    def _fake_make_movie(self: Any, request: Any) -> Any:
        # Real sync sleep — this is what would block the loop without
        # the threadpool wrap. 0.6s is enough to detect blocking with
        # margin, while keeping the test fast.
        time.sleep(0.6)
        from datetime import datetime, timezone

        from movie_maker.movie_actions_model import MakeMovieResponse, Story
        from movie_maker.movie_model import MovieModel
        from utils.common_models import ActionStatus, Session

        now = datetime.now(timezone.utc)
        return MakeMovieResponse(
            request_id=Session(
                user=Session.UserInfo(id="1"),
                project=Session.ProjectInfo(id="1"),
                version=Session.VersionInfo(id="loop-test-1"),
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

    monkeypatch.setattr(
        movie_actions.MovieActionsHandler, "make_movie", _fake_make_movie
    )

    # 2) No-op webhook so we don't talk to the network. Patch the symbol
    #    where main.py imports it from (Python binds at import time).
    import main as main_module  # noqa: WPS433

    monkeypatch.setattr(main_module, "fire_webhook", lambda *a, **kw: True)

    return app


def _v2_request_dict() -> dict[str, Any]:
    """Minimal valid /make_movie body for the FastAPI route."""
    return {
        "job_id": "loop-test-1",
        "agent": {"id": 1, "name": "Test"},
        "kondo": {"id": 1, "address": "Rua X, 0"},
        "media_urls": ["https://cdn.example.com/m1.jpg"],
        "description": "loop-test",
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


def test_make_movie_returns_2xx_with_threadpool_path(app_with_stubbed_render):
    """
    Sanity check that the route still returns a successful response
    once the render is wrapped in `run_in_threadpool`. Confirms the
    refactor didn't break the happy path.
    """
    with TestClient(app_with_stubbed_render) as client:
        resp = client.post("/make_movie", json=_v2_request_dict())
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_healthz_remains_responsive_during_render(app_with_stubbed_render):
    """
    Concurrency contract: while `/make_movie` is in flight (sync render
    sleeping for ~0.6s), `/` should still respond promptly because the
    blocking work runs in a threadpool, not on the asyncio event loop.

    We use `httpx.AsyncClient` against the live ASGI app (no real
    network) and fire both requests concurrently. The health check must
    return inside a fraction of the render duration; we assert <0.3s,
    well below the 0.6s sleep, leaving headroom for CI noise.

    With the threadpool wrap removed, the health check would only return
    after the render's full sleep — this test is the regression guard.
    """
    transport_kwargs = {"app": app_with_stubbed_render, "base_url": "http://test"}
    async with AsyncClient(**transport_kwargs) as client:
        # Kick off the long render first (don't await yet).
        render_task = asyncio.create_task(
            client.post("/make_movie", json=_v2_request_dict())
        )

        # Tiny pause so the render has definitely entered its sleep.
        await asyncio.sleep(0.05)

        # Time the health check.
        t0 = time.monotonic()
        health = await client.get("/")
        elapsed = time.monotonic() - t0

        assert health.status_code == 200
        assert elapsed < 0.3, (
            f"health check took {elapsed:.3f}s during a render — the "
            "asyncio event loop is being blocked. Verify run_in_threadpool "
            "still wraps MovieActionsHandler.make_movie in main.py."
        )

        # Drain the render so the test doesn't leak a pending task.
        render = await render_task
        assert render.status_code == 200
