"""
P9: tests for /metrics + the metrics module.

Two surfaces:
  - `task_queue.metrics` — pure key-formatting + Prometheus-text
    rendering. Unit-tested directly without Redis.
  - `GET /metrics` — patches Redis to return canned counter values
    + queue depth + heartbeat, asserts the exposition is well-formed.
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


# ---- metrics module unit tests ----

def test_build_counter_key_no_labels():
    from task_queue.metrics import _build_counter_key

    assert _build_counter_key("kondo_renders_started_total") == (
        "kondo:metrics:kondo_renders_started_total"
    )


def test_build_counter_key_sorts_labels():
    """Insertion order must not matter — same logical metric → same key."""
    from task_queue.metrics import _build_counter_key

    a = _build_counter_key("k", {"edl_id": "city_beat", "outcome": "ok"})
    b = _build_counter_key("k", {"outcome": "ok", "edl_id": "city_beat"})
    assert a == b == "kondo:metrics:k{edl_id=city_beat,outcome=ok}"


def test_parse_counter_key_roundtrips():
    from task_queue.metrics import _build_counter_key, _parse_counter_key

    key = _build_counter_key("foo", {"a": "1", "b": "2"})
    metric, labels = _parse_counter_key(key)
    assert metric == "foo"
    assert labels == {"a": "1", "b": "2"}


def test_render_prometheus_text_groups_by_metric():
    from task_queue.metrics import render_prometheus_text

    counters = [
        ("kondo_renders_started_total", {"edl_id": "city_beat"}, 5.0),
        ("kondo_renders_started_total", {"edl_id": "sonoma"}, 2.0),
        ("kondo_renders_succeeded_total", {"edl_id": "city_beat"}, 4.0),
    ]
    text = render_prometheus_text(counters)

    # Each metric gets one HELP + one TYPE line, then one row per label set.
    assert text.count("# HELP kondo_renders_started_total") == 1
    assert text.count("# TYPE kondo_renders_started_total counter") == 1
    assert 'kondo_renders_started_total{edl_id="city_beat"} 5.0' in text
    assert 'kondo_renders_started_total{edl_id="sonoma"} 2.0' in text
    assert 'kondo_renders_succeeded_total{edl_id="city_beat"} 4.0' in text


def test_render_prometheus_text_includes_gauges():
    from task_queue.metrics import render_prometheus_text

    text = render_prometheus_text([], gauges=[("kondo_queue_depth", {}, 7.0)])
    assert "# TYPE kondo_queue_depth gauge" in text
    assert "kondo_queue_depth 7.0" in text


# ---- /metrics endpoint integration ----

@pytest.fixture
def client() -> TestClient:
    from main import app

    return TestClient(app)


def test_metrics_endpoint_serves_prometheus_text_format(client: TestClient) -> None:
    """End-to-end: counter values from Redis make it into the response."""
    redis = MagicMock()

    # SCAN yields one counter key.
    async def _scan_iter(*_args: Any, **_kwargs: Any):
        yield b"kondo:metrics:kondo_renders_started_total{edl_id=city_beat}"

    redis.scan_iter = _scan_iter
    redis.get = AsyncMock(return_value=b"3")
    redis.zcard = AsyncMock(return_value=2)
    redis.aclose = AsyncMock(return_value=None)
    redis.ping = AsyncMock(return_value=True)

    # No worker heartbeat (so the gauge is omitted), simulated by a
    # second scan_iter call returning nothing.
    # We can't easily distinguish the two scan_iter calls because
    # async generators are exhausted on first iteration. Override
    # scan_iter to return different things based on the `match` arg.
    calls = {"count": 0}

    async def _scan_iter_dispatch(*args: Any, **kwargs: Any):
        match = kwargs.get("match", "")
        calls["count"] += 1
        if "metrics" in match:
            yield b"kondo:metrics:kondo_renders_started_total{edl_id=city_beat}"
        # heartbeat scan returns nothing (no worker)

    redis.scan_iter = _scan_iter_dispatch

    with patch("main.Redis.from_url", return_value=redis):
        resp = client.get("/metrics")

    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    body = resp.text
    assert "# TYPE kondo_renders_started_total counter" in body
    assert 'kondo_renders_started_total{edl_id="city_beat"} 3.0' in body
    assert "kondo_queue_depth 2.0" in body


def test_metrics_endpoint_serves_partial_when_redis_down(client: TestClient) -> None:
    """A 5xx Prometheus scrape would churn the alerting; serve 200 with empty body."""

    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise ConnectionError("simulated redis outage")

    with patch("main.Redis.from_url", side_effect=_raise):
        resp = client.get("/metrics")

    assert resp.status_code == 200
    # Empty body (no metrics were collected) — Prometheus parses this as
    # zero series, doesn't 5xx-flap.
    assert resp.text.strip() == ""
