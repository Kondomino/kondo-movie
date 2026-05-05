"""
P8: tests for `DELETE /jobs/{job_id}` real cancellation.

We patch `arq.jobs.Job` to return canned states + abort outcomes so the
tests don't need a real Redis or worker.
"""

from __future__ import annotations

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
def client() -> TestClient:
    from main import app

    return TestClient(app)


def _patch_pool() -> MagicMock:
    pool = MagicMock()
    pool.aclose = AsyncMock(return_value=None)
    return pool


def test_cancel_queued_job_removes_from_queue(client: TestClient) -> None:
    """A queued job aborts cleanly and returns cancelled=true."""
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.queued)
    job.abort = AsyncMock(return_value=True)
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.delete("/jobs/abc")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {"job_id": "abc", "cancelled": True}
    job.abort.assert_awaited_once()


def test_cancel_running_job_aborts_worker(client: TestClient) -> None:
    """In-progress jobs get the abort signal — best-effort but recorded."""
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.in_progress)
    job.abort = AsyncMock(return_value=True)
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.delete("/jobs/abc")

    assert resp.status_code == 200
    assert resp.json()["cancelled"] is True


def test_cancel_running_job_records_failed_abort(client: TestClient) -> None:
    """When the worker misses the abort signal, surface cancelled=false."""
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.in_progress)
    job.abort = AsyncMock(return_value=False)
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.delete("/jobs/abc")

    assert resp.status_code == 200
    assert resp.json()["cancelled"] is False


def test_cancel_terminal_job_is_noop(client: TestClient) -> None:
    """A complete job returns cancelled=false with a reason; no abort attempted."""
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.complete)
    job.abort = AsyncMock(return_value=True)  # tripwire — must not be called
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.delete("/jobs/abc")

    assert resp.status_code == 200
    body = resp.json()
    assert body["cancelled"] is False
    assert body["reason"] == "already complete"
    job.abort.assert_not_awaited()


def test_cancel_unknown_job_returns_404(client: TestClient) -> None:
    """arq evicts results past keep_result; surface 404 so the caller decides."""
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.not_found)
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.delete("/jobs/abc")

    assert resp.status_code == 404
