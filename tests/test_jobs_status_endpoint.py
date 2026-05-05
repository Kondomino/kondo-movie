"""
P5: tests for `GET /jobs/{job_id}/status` — the poll-fallback that
kondos-api's VideoStatusPollerService uses when a webhook is missed.

We patch `arq.jobs.Job` to return canned states so the tests don't
need a real Redis or worker.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
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


def _make_response_dict() -> dict[str, Any]:
    """Build a JSON-serializable MakeMovieResponse for a successful render."""
    from movie_maker.movie_actions_model import MakeMovieResponse, Story
    from movie_maker.movie_model import MovieModel
    from utils.common_models import ActionStatus, Session

    now = datetime.now(timezone.utc)
    full = MakeMovieResponse(
        request_id=Session(
            user=Session.UserInfo(id="1"),
            project=Session.ProjectInfo(id="1"),
            version=Session.VersionInfo(id="abc"),
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
    return full.model_dump(mode="json")


def test_status_returns_queued_when_job_is_in_arq_queue(client: TestClient) -> None:
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.queued)
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.get("/jobs/abc/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "job_id": "abc",
        "phase": "queued",
        "progress": 0,
        "output_url": None,
        "thumbnail_url": None,
        "duration_seconds": None,
        "error": None,
    }


def test_status_returns_processing_when_job_in_progress(client: TestClient) -> None:
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.in_progress)
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.get("/jobs/abc/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "processing"
    assert body["progress"] == 50  # midpoint placeholder


def test_status_returns_done_with_output_url_on_complete_success(
    client: TestClient,
) -> None:
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.complete)
    result_info = MagicMock()
    result_info.success = True
    result_info.result = _make_response_dict()
    job.result_info = AsyncMock(return_value=result_info)
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.get("/jobs/abc/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "done"
    assert body["progress"] == 100
    assert body["output_url"] == "https://cdn.example.com/out.mp4"
    assert body["error"] is None


def test_status_returns_failed_when_job_failed(client: TestClient) -> None:
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.complete)
    result_info = MagicMock()
    result_info.success = False
    result_info.result = "RuntimeError: ffmpeg crashed"
    job.result_info = AsyncMock(return_value=result_info)
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.get("/jobs/abc/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "failed"
    assert body["progress"] == 100
    assert "ffmpeg" in (body["error"] or "")


def test_status_returns_404_when_job_not_found(client: TestClient) -> None:
    """
    arq evicts results past keep_result. /readyz can't tell the difference
    between "never existed" and "evicted", so we surface 404 and let
    kondos-api's poller decide whether to mark the row failed.
    """
    from arq.jobs import JobStatus

    job = MagicMock()
    job.status = AsyncMock(return_value=JobStatus.not_found)
    pool = _patch_pool()

    with patch("main.create_pool", AsyncMock(return_value=pool)), patch(
        "main.Job", return_value=job
    ):
        resp = client.get("/jobs/abc/status")

    assert resp.status_code == 404
