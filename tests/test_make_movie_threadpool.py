"""
P2 of the video-render-reliability plan: prove that `/make_movie` no
longer blocks the asyncio event loop during a render. Without
`run_in_threadpool` wrapping the sync render and webhook calls, a
real /healthz probe would queue behind the 60-90s blocking work,
Fly would mark the machine unhealthy, and the render would die.

Strategy:
- Set safe dummy values for env vars that storage_manager validates
  at import time (R2 creds), since this is the first test in the
  suite to import movie_actions.
- Monkeypatch `MovieActionsHandler.make_movie` to a `time.sleep(0.6)`
  stub that simulates the long sync render without doing real work.
- Monkeypatch `fire_webhook` to a no-op (no network calls).
- Drive `/make_movie` from a worker thread and `GET /` from the main
  thread concurrently. With the threadpool wrap in place, the health
  check should return well under 0.3s. Without it, the health check
  would queue behind the 0.6s blocking render — that gap is the
  regression guard.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient


# Set R2 dummies BEFORE any kondo-movie module gets imported by the
# fixture below. storage_manager validates these at import time;
# without them, just touching `from movie_maker import movie_actions`
# raises ValueError. Local dev gets the values from .env via
# python-dotenv, but CI runs without one. Dummies must never reach a
# real bucket — we monkeypatch the render to skip storage entirely.
_R2_DUMMIES = {
    "CLOUDFLARE_R2_KEY_ID": "test-r2-key-id",
    "CLOUDFLARE_R2_ACCESS_KEY": "test-r2-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://test-r2.example.com",
}
for _k, _v in _R2_DUMMIES.items():
    os.environ.setdefault(_k, _v)


@pytest.fixture
def app_with_stubbed_render(monkeypatch: pytest.MonkeyPatch):
    """
    Yield a FastAPI app whose render path is replaced by a synchronous
    sleep + a synthetic success response, and whose webhook is a no-op.
    Returns (app, sleep_seconds) so tests can size their timing assertions.
    """
    from main import app  # noqa: WPS433
    from movie_maker import movie_actions  # noqa: WPS433

    SLEEP_SECONDS = 0.6

    def _fake_make_movie(self: Any, request: Any) -> Any:
        """
        Real sync sleep — this is what would block the loop without
        the threadpool wrap. We return a fully-typed `MakeMovieResponse`
        so FastAPI's response_model validation passes.
        """
        time.sleep(SLEEP_SECONDS)
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

    # No-op webhook so we don't talk to the network. Patch the symbol
    # at the import site (main.py) since Python rebinds at import time.
    import main as main_module  # noqa: WPS433

    monkeypatch.setattr(main_module, "fire_webhook", lambda *a, **kw: True)

    return app, SLEEP_SECONDS


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
    app, _ = app_with_stubbed_render
    with TestClient(app) as client:
        resp = client.post("/make_movie", json=_v2_request_dict())
    assert resp.status_code == 200, resp.text


def test_healthz_remains_responsive_during_render(app_with_stubbed_render):
    """
    Concurrency contract: while `/make_movie` is in flight (sync render
    sleeping for ~0.6s), `GET /` should still respond promptly because
    the blocking work runs in a threadpool, not on the asyncio event
    loop.

    We fire the long render from a worker thread and time the health
    check from the main thread. Both go through the same `TestClient`
    (which serialises requests at the transport layer but allows the
    ASGI app's threadpool to run actual blocking work concurrently).

    Thresholds:
      - sleep_seconds = 0.6 — the simulated render time.
      - health-check budget = 0.3s — half the render time, plenty of
        headroom for CI noise. With the threadpool wrap, the health
        check completes in microseconds. Without it, it would queue
        behind the full sleep_seconds.
    """
    app, sleep_seconds = app_with_stubbed_render

    with TestClient(app) as client:
        render_response: dict[str, Any] = {}
        render_error: dict[str, BaseException] = {}

        def _do_render() -> None:
            try:
                render_response["resp"] = client.post(
                    "/make_movie", json=_v2_request_dict()
                )
            except BaseException as exc:  # noqa: BLE001
                render_error["err"] = exc

        render_thread = threading.Thread(target=_do_render, daemon=True)
        render_thread.start()

        # Tiny pause so the render has definitely entered its sleep
        # before we fire the health check. Has to be much smaller than
        # sleep_seconds so we're sampling the middle of the render.
        time.sleep(0.1)

        t0 = time.monotonic()
        health = client.get("/")
        elapsed = time.monotonic() - t0

        assert health.status_code == 200
        assert elapsed < 0.3, (
            f"health check took {elapsed:.3f}s during a render — the "
            "asyncio event loop is being blocked. Verify run_in_threadpool "
            "still wraps MovieActionsHandler.make_movie in main.py."
        )

        # Drain the worker thread so the test doesn't leak.
        render_thread.join(timeout=sleep_seconds + 1.0)
        assert not render_thread.is_alive(), "render worker thread didn't finish"
        assert "err" not in render_error, render_error.get("err")
        assert render_response["resp"].status_code == 200
