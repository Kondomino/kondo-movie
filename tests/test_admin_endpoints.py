"""
P12: tests for the operator dashboard endpoints.

  GET  /admin/queue
  GET  /admin/dead-webhooks
  POST /admin/dead-webhooks/replay

All require X-Internal-Token = KONDO_WEBHOOK_TOKEN env var. Empty env
= closed-by-default (401 even with no header) so a misconfigured deploy
can't accidentally expose the endpoints.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


_R2_DUMMIES = {
    "CLOUDFLARE_R2_KEY_ID": "test-r2-key-id",
    "CLOUDFLARE_R2_ACCESS_KEY": "test-r2-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://test-r2.example.com",
}
for _k, _v in _R2_DUMMIES.items():
    os.environ.setdefault(_k, _v)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """TestClient with KONDO_WEBHOOK_TOKEN set to a known value."""
    monkeypatch.setenv("KONDO_WEBHOOK_TOKEN", "test-secret")
    from main import app

    return TestClient(app)


def _patch_pool() -> MagicMock:
    pool = MagicMock()
    pool.aclose = AsyncMock(return_value=None)
    return pool


def _patch_redis() -> MagicMock:
    redis = MagicMock()
    redis.aclose = AsyncMock(return_value=None)
    return redis


# ---- Auth ----

def test_admin_queue_requires_token(client: TestClient) -> None:
    resp = client.get("/admin/queue")
    assert resp.status_code == 401


def test_admin_queue_rejects_wrong_token(client: TestClient) -> None:
    resp = client.get("/admin/queue", headers={"X-Internal-Token": "wrong"})
    assert resp.status_code == 401


def test_admin_endpoints_closed_when_token_unset(monkeypatch) -> None:
    """
    Even with the right header, missing-server-side env = 401. A
    misconfigured deploy must not accidentally expose admin surface.
    """
    monkeypatch.setenv("KONDO_WEBHOOK_TOKEN", "")
    from main import app

    with TestClient(app) as c:
        resp = c.get("/admin/queue", headers={"X-Internal-Token": "anything"})
    assert resp.status_code == 401
    assert "not configured" in resp.json()["detail"].lower()


# ---- /admin/queue ----

def test_admin_queue_returns_depth_and_dead_letter_count(client: TestClient) -> None:
    redis = _patch_redis()
    redis.zcard = AsyncMock(side_effect=[5, 2])  # arq:queue first, then dead-letter
    # No worker heartbeat seeded — keep the field None.

    async def _scan_iter(*_args: Any, **_kwargs: Any):
        return
        yield  # pragma: no cover — empty async generator

    redis.scan_iter = _scan_iter
    redis.get = AsyncMock(return_value=None)

    with patch("main.Redis.from_url", return_value=redis):
        resp = client.get("/admin/queue", headers={"X-Internal-Token": "test-secret"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["queue_depth"] == 5
    assert body["dead_letter_count"] == 2
    assert body["worker_heartbeat_age_seconds"] is None
    assert body["error"] is None


# ---- /admin/dead-webhooks ----

def test_admin_dead_webhooks_lists_zset(client: TestClient) -> None:
    """ZREVRANGE returns newest-first; payloads JSON-decoded for the operator."""
    redis = _patch_redis()
    record_a = json.dumps(
        {
            "webhook_url": "https://api.test/cb",
            "payload": {"phase": "done"},
            "reason": "http 503 (max tries exhausted)",
            "attempts": 5,
            "job_id": "job-A",
            "dead_at": 1000,
        }
    )
    record_b = json.dumps(
        {
            "webhook_url": "https://api.test/cb",
            "payload": {"phase": "failed"},
            "reason": "network: ConnectionError",
            "attempts": 5,
            "job_id": "job-B",
            "dead_at": 2000,
        }
    )
    redis.zrevrange = AsyncMock(return_value=[record_b.encode(), record_a.encode()])

    with patch("main.Redis.from_url", return_value=redis):
        resp = client.get(
            "/admin/dead-webhooks", headers={"X-Internal-Token": "test-secret"}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    # newest first per ZREVRANGE
    assert body["items"][0]["job_id"] == "job-B"
    assert body["items"][1]["job_id"] == "job-A"
    assert body["items"][0]["reason"].startswith("network:")


# ---- /admin/dead-webhooks/replay ----

def test_replay_re_enqueues_webhook(client: TestClient) -> None:
    job = MagicMock()
    pool = _patch_pool()
    pool.enqueue_job = AsyncMock(return_value=job)

    body = {
        "webhook_url": "https://api.test/cb",
        "payload": {"phase": "done", "progress": 100},
        "job_id": "job-X",
    }

    with patch("main.create_pool", AsyncMock(return_value=pool)):
        resp = client.post(
            "/admin/dead-webhooks/replay",
            headers={"X-Internal-Token": "test-secret"},
            json=body,
        )

    assert resp.status_code == 200
    out = resp.json()
    assert out["replayed"] is True
    assert out["replay_job_id"].startswith("job-X:replay:")

    pool.enqueue_job.assert_awaited_once()
    args, kwargs = pool.enqueue_job.call_args
    assert args[0] == "deliver_webhook"
    assert args[1] == "https://api.test/cb"
    assert kwargs["_job_id"] == out["replay_job_id"]


def test_replay_rejects_invalid_body(client: TestClient) -> None:
    """Both webhook_url and payload (object) are required."""
    with patch("main.create_pool", AsyncMock(return_value=_patch_pool())):
        resp = client.post(
            "/admin/dead-webhooks/replay",
            headers={"X-Internal-Token": "test-secret"},
            json={"webhook_url": "https://x"},  # missing payload
        )
    assert resp.status_code == 400
