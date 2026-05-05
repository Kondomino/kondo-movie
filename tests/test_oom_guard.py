"""
P11: tests for the OOM pre-render guard.

Three surfaces:
  - `available_memory_bytes` parses /proc/meminfo's MemAvailable
  - `check_memory_pressure` raises FfmpegOomError below the threshold
  - `render_movie` short-circuits when the guard trips, fires a
    failed webhook, and returns the OOM-classed failure dict

Tests for the parser monkeypatch the file path so we don't depend on
the host's actual memory state.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


_R2_DUMMIES = {
    "CLOUDFLARE_R2_KEY_ID": "test-r2-key-id",
    "CLOUDFLARE_R2_ACCESS_KEY": "test-r2-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://test-r2.example.com",
}
for _k, _v in _R2_DUMMIES.items():
    os.environ.setdefault(_k, _v)


# ---- available_memory_bytes ----

def test_parses_mem_available_from_proc_meminfo(tmp_path, monkeypatch):
    from task_queue import oom

    fake = tmp_path / "meminfo"
    fake.write_text(
        "MemTotal:        4194304 kB\n"
        "MemFree:          200000 kB\n"
        "MemAvailable:    2000000 kB\n"
        "Buffers:           50000 kB\n"
    )
    monkeypatch.setattr(oom, "_PROC_MEMINFO", fake)

    assert oom.available_memory_bytes() == 2000000 * 1024


def test_returns_none_when_meminfo_unreadable(tmp_path, monkeypatch):
    """macOS / dev: no /proc/meminfo. Must not crash, must not lie."""
    from task_queue import oom

    monkeypatch.setattr(oom, "_PROC_MEMINFO", tmp_path / "does-not-exist")

    assert oom.available_memory_bytes() is None


def test_returns_none_when_mem_available_field_missing(tmp_path, monkeypatch):
    """Some kernels older than 3.14 don't expose MemAvailable. Skip cleanly."""
    from task_queue import oom

    fake = tmp_path / "meminfo"
    fake.write_text("MemTotal: 4194304 kB\nMemFree: 200000 kB\n")
    monkeypatch.setattr(oom, "_PROC_MEMINFO", fake)

    assert oom.available_memory_bytes() is None


# ---- check_memory_pressure ----

def test_raises_oom_below_threshold(tmp_path, monkeypatch):
    from task_queue import oom

    fake = tmp_path / "meminfo"
    fake.write_text("MemAvailable:     500000 kB\n")  # ~500 MB, below 1GB default
    monkeypatch.setattr(oom, "_PROC_MEMINFO", fake)
    monkeypatch.delenv("KONDO_MOVIE_MIN_AVAILABLE_BYTES", raising=False)

    with pytest.raises(oom.FfmpegOomError) as exc_info:
        oom.check_memory_pressure()
    assert exc_info.value.available_bytes == 500000 * 1024
    assert "memory pressure" in str(exc_info.value).lower()


def test_passes_silently_above_threshold(tmp_path, monkeypatch):
    from task_queue import oom

    fake = tmp_path / "meminfo"
    fake.write_text("MemAvailable:    3000000 kB\n")  # ~3 GB, above 1GB default
    monkeypatch.setattr(oom, "_PROC_MEMINFO", fake)
    monkeypatch.delenv("KONDO_MOVIE_MIN_AVAILABLE_BYTES", raising=False)

    oom.check_memory_pressure()  # no raise


def test_no_op_when_meminfo_unreadable(tmp_path, monkeypatch):
    """Dev on macOS — silent skip rather than failing every render."""
    from task_queue import oom

    monkeypatch.setattr(oom, "_PROC_MEMINFO", tmp_path / "does-not-exist")

    oom.check_memory_pressure()  # no raise


def test_threshold_overridable_via_env(tmp_path, monkeypatch):
    from task_queue import oom

    fake = tmp_path / "meminfo"
    fake.write_text("MemAvailable:    2000000 kB\n")  # ~2 GB
    monkeypatch.setattr(oom, "_PROC_MEMINFO", fake)
    # Set threshold higher than available so it trips.
    monkeypatch.setenv(
        "KONDO_MOVIE_MIN_AVAILABLE_BYTES", str(3 * 1024 * 1024 * 1024)
    )

    with pytest.raises(oom.FfmpegOomError):
        oom.check_memory_pressure()


# ---- render_movie integration ----

def _v2_request_dict() -> dict[str, Any]:
    return {
        "job_id": "p11-test-job-1",
        "agent": {"id": 1, "name": "Test"},
        "kondo": {"id": 1, "address": "Rua X, 0"},
        "media_urls": ["https://cdn.example.com/m1.jpg"],
        "description": "p11-test",
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


@pytest.mark.asyncio
async def test_render_short_circuits_on_oom_guard(monkeypatch):
    """
    When check_memory_pressure raises, render_movie must NOT call
    MovieActionsHandler. It fires a failed webhook + returns the
    OOM-classed failure dict.
    """
    from task_queue import oom, tasks
    from movie_maker import movie_actions

    handler_called = {"count": 0}

    def _tripwire(self: Any, request: Any) -> Any:
        handler_called["count"] += 1
        return None

    monkeypatch.setattr(movie_actions.MovieActionsHandler, "make_movie", _tripwire)

    def _trip(*_args: Any, **_kwargs: Any) -> None:
        raise oom.FfmpegOomError("simulated", available_bytes=200_000_000)

    monkeypatch.setattr(tasks, "check_memory_pressure", _trip)

    redis = MagicMock()
    redis.enqueue_job = AsyncMock(return_value=MagicMock())
    ctx = {"redis": redis, "job_id": "p11-test-job-1"}

    result = await tasks.render_movie(ctx, _v2_request_dict())

    # Render handler never ran.
    assert handler_called["count"] == 0
    # Failure dict carries the oom class.
    assert result["result"]["state"] == "Failure"
    assert result["failure_class"] == "oom"
    # Failed webhook got enqueued via deliver_webhook.
    redis.enqueue_job.assert_awaited_once()
    args, kwargs = redis.enqueue_job.call_args
    assert args[0] == "deliver_webhook"
    assert args[2]["phase"] == "failed"
    assert kwargs["_job_id"] == "p11-test-job-1:webhook"
