"""
P3 of the video-render-reliability plan: cover the new health/readiness
split.

Three tests track the contract:
  1. /healthz is cheap — no Redis call, no other deps. The Fly probe
     targets this, so a slow Redis must not be able to flap the machine
     state.
  2. /readyz returns degraded when Redis is up but no worker heartbeat
     exists. This is the expected baseline state until P4 ships the
     worker process — surfacing it explicitly prevents confusion with a
     real outage.
  3. /readyz returns ok when a fresh heartbeat is present in Redis.
     Pre-seeds a fake heartbeat key directly via the redis client mock.

We mock `redis.asyncio.Redis.from_url` so the tests run without a real
Redis server.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# Same R2 dummies as test_make_movie_threadpool — needed because
# importing main pulls movie_actions which validates R2 creds at
# import time.
_R2_DUMMIES = {
    "CLOUDFLARE_R2_KEY_ID": "test-r2-key-id",
    "CLOUDFLARE_R2_ACCESS_KEY": "test-r2-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://test-r2.example.com",
}
for _k, _v in _R2_DUMMIES.items():
    os.environ.setdefault(_k, _v)


@pytest.fixture
def client() -> TestClient:
    from main import app  # noqa: WPS433

    return TestClient(app)


def _patched_redis(*, ping_ok: bool = True, scan_keys: list[bytes] | None = None,
                   get_value: bytes | None = None) -> MagicMock:
    """
    Build a `Redis` instance double whose async methods return the values
    the tests need. `scan_iter` yields `scan_keys`; `get` returns
    `get_value`; `ping` returns `ping_ok`.
    """
    redis = MagicMock()
    redis.ping = AsyncMock(return_value=ping_ok)

    async def _scan_iter(*_args: Any, **_kwargs: Any):
        for key in (scan_keys or []):
            yield key

    redis.scan_iter = _scan_iter
    redis.get = AsyncMock(return_value=get_value)
    redis.aclose = AsyncMock(return_value=None)
    return redis


def test_healthz_returns_200_no_deps(client: TestClient) -> None:
    """
    /healthz is the Fly probe target. It must not touch Redis or any
    other dep — that's the entire reason we split it from /readyz.
    Patch Redis.from_url to a sentinel and assert it was NEVER called.
    """
    with patch("main.Redis.from_url") as from_url:
        from_url.return_value = MagicMock()  # tripwire
        resp = client.get("/healthz")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert from_url.call_count == 0, (
        "/healthz must not call Redis.from_url — that's /readyz's job"
    )


def test_readyz_pings_redis_and_returns_degraded_without_worker(
    client: TestClient,
) -> None:
    """
    With Redis up but zero worker heartbeat keys (the expected baseline
    until P4 ships), /readyz reports `degraded` (HTTP 503). Surfaces
    `worker: no-heartbeat` so it's not confused with a real outage.
    """
    redis_double = _patched_redis(ping_ok=True, scan_keys=[])
    with patch("main.Redis.from_url", return_value=redis_double):
        resp = client.get("/readyz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["redis"] is True
    assert body["worker"] == "no-heartbeat"
    assert body["worker_heartbeat_age_seconds"] is None
    redis_double.ping.assert_awaited()
    redis_double.aclose.assert_awaited()


def test_readyz_returns_ok_with_recent_heartbeat(client: TestClient) -> None:
    """
    Seed a fresh heartbeat: SCAN returns one key, GET returns a recent
    UTC ISO8601 timestamp. /readyz flips to `ok` (HTTP 200).
    """
    fresh_iso = datetime.now(timezone.utc).isoformat().encode("utf-8")
    redis_double = _patched_redis(
        ping_ok=True,
        scan_keys=[b"kondo:worker:test-machine:heartbeat"],
        get_value=fresh_iso,
    )
    with patch("main.Redis.from_url", return_value=redis_double):
        resp = client.get("/readyz")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["redis"] is True
    assert body["worker"] == "ok"
    assert body["worker_heartbeat_age_seconds"] is not None
    assert body["worker_heartbeat_age_seconds"] < 5  # just-written


def test_readyz_returns_degraded_when_redis_unreachable(
    client: TestClient,
) -> None:
    """
    When Redis itself is down, /readyz must surface that as 503 with a
    diagnostic in `redis_error`. Catches the regression where a slow
    Redis would block the readiness probe forever.
    """
    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise ConnectionError("simulated redis outage")

    with patch("main.Redis.from_url", side_effect=_raise):
        resp = client.get("/readyz")

    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["redis"] is False
    assert "ConnectionError" in (body["redis_error"] or "")


def test_root_alias_still_returns_200(client: TestClient) -> None:
    """
    `/` is kept as a back-compat alias of /healthz. Anything probing the
    old endpoint should still get a 200.
    """
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
