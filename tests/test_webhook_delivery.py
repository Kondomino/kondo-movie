"""
P6: tests for the durable webhook delivery task.

Coverage:
  - 2xx response → returns success, no retry
  - 5xx response → raises arq.Retry with the right backoff
  - 4xx (non-408/429) → permanent fail, lands in dead-letter
  - max-tries exhaustion on retryable status → lands in dead-letter
  - network error → raises Retry until last attempt, then dead-letters

`post_webhook_once` is patched in each test so no real HTTP is made.
The arq `redis` in the ctx is a MagicMock with the ZADD/EXPIRE methods
deliver_webhook needs for dead-lettering.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from arq import Retry


_R2_DUMMIES = {
    "CLOUDFLARE_R2_KEY_ID": "test-r2-key-id",
    "CLOUDFLARE_R2_ACCESS_KEY": "test-r2-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://test-r2.example.com",
}
for _k, _v in _R2_DUMMIES.items():
    os.environ.setdefault(_k, _v)


def _ctx(*, job_try: int = 1, job_id: str = "test-job") -> dict[str, Any]:
    """Stub arq context. ZADD/EXPIRE on redis are AsyncMocks for dead-letter."""
    redis = MagicMock()
    redis.zadd = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    return {"job_try": job_try, "job_id": job_id, "redis": redis}


def _payload() -> dict[str, Any]:
    return {"phase": "done", "progress": 100, "output_url": "https://cdn/x.mp4"}


@pytest.mark.asyncio
async def test_delivers_on_2xx():
    from task_queue.tasks import deliver_webhook

    ctx = _ctx()
    with patch("task_queue.tasks.post_webhook_once", return_value=200):
        result = await deliver_webhook(ctx, "https://api.test/cb", _payload())

    assert result == {"delivered": True, "status": 200, "tries": 1}
    ctx["redis"].zadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_retries_on_5xx_with_backoff():
    """5xx → arq.Retry with the first-attempt backoff (10s = 10000ms)."""
    from task_queue.tasks import deliver_webhook, WEBHOOK_RETRY_BACKOFF_SECONDS

    ctx = _ctx(job_try=1)
    with patch("task_queue.tasks.post_webhook_once", return_value=503):
        with pytest.raises(Retry) as exc_info:
            await deliver_webhook(ctx, "https://api.test/cb", _payload())

    # arq stores defer in milliseconds via Retry.defer_score.
    assert exc_info.value.defer_score == WEBHOOK_RETRY_BACKOFF_SECONDS[0] * 1000


@pytest.mark.asyncio
async def test_retries_on_408_and_429():
    from task_queue.tasks import deliver_webhook

    for transient_code in (408, 429):
        ctx = _ctx(job_try=2)
        with patch("task_queue.tasks.post_webhook_once", return_value=transient_code):
            with pytest.raises(Retry):
                await deliver_webhook(ctx, "https://api.test/cb", _payload())


@pytest.mark.asyncio
async def test_permanent_fail_on_400(monkeypatch):
    """
    Non-retryable 4xx (e.g. 400 bad request) goes straight to dead-letter
    without burning retries.
    """
    from task_queue.tasks import deliver_webhook

    ctx = _ctx(job_try=1)
    with patch("task_queue.tasks.post_webhook_once", return_value=400):
        result = await deliver_webhook(ctx, "https://api.test/cb", _payload())

    assert result["delivered"] is False
    assert "http 400" in result["reason"]
    assert result["tries"] == 1
    ctx["redis"].zadd.assert_awaited_once()
    # Member is the JSON record; the score is "now". Check the record
    # captures everything the operator needs to triage.
    args, kwargs = ctx["redis"].zadd.call_args
    member_dict, score = next(iter(args[1].items()))
    record = json.loads(member_dict)
    assert record["webhook_url"] == "https://api.test/cb"
    assert record["payload"]["phase"] == "done"
    assert record["reason"] == "http 400"
    assert record["attempts"] == 1
    assert record["job_id"] == "test-job"


@pytest.mark.asyncio
async def test_lands_in_dead_letter_after_max_tries_on_5xx():
    """Last-attempt 5xx should dead-letter rather than re-raise Retry."""
    from task_queue.tasks import deliver_webhook, WEBHOOK_MAX_TRIES

    ctx = _ctx(job_try=WEBHOOK_MAX_TRIES)
    with patch("task_queue.tasks.post_webhook_once", return_value=500):
        result = await deliver_webhook(ctx, "https://api.test/cb", _payload())

    assert result["delivered"] is False
    assert "max tries exhausted" in result["reason"]
    assert result["tries"] == WEBHOOK_MAX_TRIES
    ctx["redis"].zadd.assert_awaited_once()


@pytest.mark.asyncio
async def test_network_error_retries_then_dead_letters():
    from notification.engine_webhook import WebhookNetworkError
    from task_queue.tasks import deliver_webhook, WEBHOOK_MAX_TRIES

    cause = ConnectionError("connection refused")

    # Retry on intermediate attempts.
    ctx = _ctx(job_try=2)
    with patch(
        "task_queue.tasks.post_webhook_once",
        side_effect=WebhookNetworkError(cause),
    ):
        with pytest.raises(Retry):
            await deliver_webhook(ctx, "https://api.test/cb", _payload())

    # Dead-letter on the last attempt.
    ctx_last = _ctx(job_try=WEBHOOK_MAX_TRIES)
    with patch(
        "task_queue.tasks.post_webhook_once",
        side_effect=WebhookNetworkError(cause),
    ):
        result = await deliver_webhook(
            ctx_last, "https://api.test/cb", _payload()
        )

    assert result["delivered"] is False
    assert result["reason"].startswith("network:")
    assert result["tries"] == WEBHOOK_MAX_TRIES
    ctx_last["redis"].zadd.assert_awaited_once()
