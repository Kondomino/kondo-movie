"""
P10: tests for JSON-mode logging.

Two surfaces:
  - `_extract_tag` — pure function, unit-testable.
  - `_json_sink` — emits to stdout in JSON. We capture stdout and
    parse the line back to verify the fields make it through.

The singleton SingletonLogger wires `_json_sink` only when the
LOG_FORMAT env var is `json` at module-import time. Tests use the
sink directly so they don't have to monkey with the singleton.
"""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from datetime import datetime, timezone

import pytest


_R2_DUMMIES = {
    "CLOUDFLARE_R2_KEY_ID": "test-r2-key-id",
    "CLOUDFLARE_R2_ACCESS_KEY": "test-r2-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://test-r2.example.com",
}
for _k, _v in _R2_DUMMIES.items():
    os.environ.setdefault(_k, _v)


def test_extract_tag_pulls_leading_bracketed_token():
    from logger import _extract_tag

    assert _extract_tag("[VIDEO-WORKER] render started") == "VIDEO-WORKER"
    assert _extract_tag("[VIDEO-WEBHOOK] delivered status=200") == "VIDEO-WEBHOOK"


def test_extract_tag_returns_none_without_tag():
    from logger import _extract_tag

    assert _extract_tag("plain log line") is None
    # lowercase doesn't match — tags are uppercase by convention
    assert _extract_tag("[video-worker] foo") is None


class _FakeLevel:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeMessage:
    """Mimics the shape loguru passes to a sink (`message.record`)."""

    def __init__(self, *, msg: str, extras: dict | None = None, level: str = "INFO"):
        self.record = {
            "time": datetime(2026, 5, 5, 12, 34, 56, tzinfo=timezone.utc),
            "level": _FakeLevel(level),
            "message": msg,
            "name": "test",
            "extra": extras or {},
            "exception": None,
        }


def _capture_json_emit(message: _FakeMessage) -> dict:
    from logger import _json_sink

    buf = io.StringIO()
    with redirect_stdout(buf):
        _json_sink(message)
    line = buf.getvalue().strip()
    return json.loads(line)


def test_json_sink_emits_top_level_known_fields():
    msg = _FakeMessage(
        msg="[VIDEO-WORKER] render started",
        extras={
            "engine_job_id": "abc-123",
            "kondo_id": 42,
            "agent_id": 7,
            "attempt": 2,
        },
    )
    record = _capture_json_emit(msg)

    assert record["msg"] == "[VIDEO-WORKER] render started"
    assert record["tag"] == "VIDEO-WORKER"
    assert record["level"] == "INFO"
    assert record["engine_job_id"] == "abc-123"
    assert record["kondo_id"] == 42
    assert record["agent_id"] == 7
    assert record["attempt"] == 2
    assert record["ts"] == "2026-05-05T12:34:56+00:00"


def test_json_sink_buckets_unknown_extras_under_extra_key():
    msg = _FakeMessage(
        msg="something happened",
        extras={"engine_job_id": "abc", "weird_thing": "value"},
    )
    record = _capture_json_emit(msg)

    assert record["engine_job_id"] == "abc"
    # Unknown keys live under `extra` to keep the top-level shape stable
    # for APL queries; we don't want a free-for-all schema.
    assert "extra" in record
    assert record["extra"]["weird_thing"] == "value"


def test_json_sink_handles_no_extras():
    msg = _FakeMessage(msg="plain message")
    record = _capture_json_emit(msg)
    assert record["msg"] == "plain message"
    assert record["tag"] is None
    assert "extra" not in record
