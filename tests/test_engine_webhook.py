"""
Unit tests for the outbound lifecycle webhook (kondo-movie → kondos-api).

Stdlib `urllib` is mocked at the module level so no real network IO happens.
"""

from unittest.mock import patch, MagicMock

import pytest

from notification import engine_webhook


def test_skips_when_webhook_url_is_none():
    """No URL → no call, returns False, no errors raised."""
    with patch("notification.engine_webhook.urllib.request.urlopen") as mock_urlopen:
        ok = engine_webhook.fire_webhook(None, {"phase": "done", "progress": 100})
    assert ok is False
    mock_urlopen.assert_not_called()


def test_skips_when_token_env_unset(monkeypatch):
    """Without KONDO_WEBHOOK_TOKEN we don't burn a round-trip; we know kondos-api will reject."""
    monkeypatch.delenv(engine_webhook.ENV_TOKEN, raising=False)
    with patch("notification.engine_webhook.urllib.request.urlopen") as mock_urlopen:
        ok = engine_webhook.fire_webhook("http://api.test/cb", {"phase": "done", "progress": 100})
    assert ok is False
    mock_urlopen.assert_not_called()


def test_posts_with_token_header_and_json_body(monkeypatch):
    monkeypatch.setenv(engine_webhook.ENV_TOKEN, "shh")
    fake_resp = MagicMock()
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)
    fake_resp.status = 204

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.headers)
        captured["body"] = req.data
        captured["timeout"] = timeout
        return fake_resp

    with patch("notification.engine_webhook.urllib.request.urlopen", side_effect=fake_urlopen):
        ok = engine_webhook.fire_webhook(
            "http://api.test/internal/videos/77/callback",
            {"phase": "done", "progress": 100, "output_url": "r2://final.mp4"},
        )

    assert ok is True
    assert captured["method"] == "POST"
    assert captured["url"] == "http://api.test/internal/videos/77/callback"
    # urllib lowercases the canonical case of headers; check via case-insensitive
    headers_lower = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers_lower["x-internal-token"] == "shh"
    assert headers_lower["content-type"] == "application/json"
    # Body is the JSON-encoded payload
    import json
    assert json.loads(captured["body"]) == {
        "phase": "done",
        "progress": 100,
        "output_url": "r2://final.mp4",
    }


def test_returns_false_on_http_error(monkeypatch):
    import urllib.error

    monkeypatch.setenv(engine_webhook.ENV_TOKEN, "shh")
    err = urllib.error.HTTPError(
        url="http://api.test/cb", code=401, msg="Unauthorized", hdrs=None, fp=None,
    )
    with patch("notification.engine_webhook.urllib.request.urlopen", side_effect=err):
        ok = engine_webhook.fire_webhook("http://api.test/cb", {"phase": "done", "progress": 100})
    assert ok is False


def test_returns_false_on_url_error(monkeypatch):
    import urllib.error

    monkeypatch.setenv(engine_webhook.ENV_TOKEN, "shh")
    err = urllib.error.URLError("connection refused")
    with patch("notification.engine_webhook.urllib.request.urlopen", side_effect=err):
        ok = engine_webhook.fire_webhook("http://api.test/cb", {"phase": "done", "progress": 100})
    assert ok is False


def test_returns_false_on_non_2xx(monkeypatch):
    monkeypatch.setenv(engine_webhook.ENV_TOKEN, "shh")
    fake_resp = MagicMock()
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)
    fake_resp.status = 503
    with patch("notification.engine_webhook.urllib.request.urlopen", return_value=fake_resp):
        ok = engine_webhook.fire_webhook("http://api.test/cb", {"phase": "done", "progress": 100})
    assert ok is False
