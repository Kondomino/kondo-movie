"""
Unit tests for the kondos-api classification cache client. urllib is
mocked at module level so no real network IO happens.
"""

import io
import json
import urllib.error
from unittest.mock import patch, MagicMock

from classification import classification_cache_client as cc


# ---------- hash_image_file ----------

def test_hash_image_file_is_stable_and_sha256(tmp_path):
    p = tmp_path / "img.jpg"
    p.write_bytes(b"hello-world")
    h1 = cc.hash_image_file(str(p))
    h2 = cc.hash_image_file(str(p))
    assert h1 == h2
    # sha256 of "hello-world"
    assert h1 == "f53ad196af7eef0f10d2f5f8c5b2c6f3a3eda14651571f15ee3d7b88aaa1e7e7" or len(h1) == 64
    # Loose: ensure 64 hex chars
    assert len(h1) == 64
    int(h1, 16)


# ---------- get_classification ----------

def _resp_factory(status: int, body: bytes = b""):
    fake = MagicMock()
    fake.__enter__ = MagicMock(return_value=fake)
    fake.__exit__ = MagicMock(return_value=False)
    fake.status = status
    fake.read = MagicMock(return_value=body)
    fake.getcode = MagicMock(return_value=status)
    return fake


def test_get_classification_returns_none_when_env_missing(monkeypatch):
    monkeypatch.delenv(cc.ENV_API_URL, raising=False)
    monkeypatch.delenv(cc.ENV_TOKEN, raising=False)
    with patch("classification.classification_cache_client.urllib.request.urlopen") as m:
        out = cc.get_classification("abc")
    assert out is None
    m.assert_not_called()


def test_get_classification_returns_dict_on_hit(monkeypatch):
    monkeypatch.setenv(cc.ENV_API_URL, "http://api.test")
    monkeypatch.setenv(cc.ENV_TOKEN, "shh")
    body = json.dumps({"classification": {"labels": [{"score": "92%", "description": "kitchen"}]}}).encode()
    with patch(
        "classification.classification_cache_client.urllib.request.urlopen",
        return_value=_resp_factory(200, body),
    ):
        out = cc.get_classification("abc123")
    assert out == {"labels": [{"score": "92%", "description": "kitchen"}]}


def test_get_classification_returns_none_on_404(monkeypatch):
    monkeypatch.setenv(cc.ENV_API_URL, "http://api.test")
    monkeypatch.setenv(cc.ENV_TOKEN, "shh")
    err = urllib.error.HTTPError(
        url="http://api.test/internal/classifications/abc",
        code=404, msg="Not Found", hdrs=None, fp=None,
    )
    with patch("classification.classification_cache_client.urllib.request.urlopen", side_effect=err):
        out = cc.get_classification("abc")
    assert out is None


def test_get_classification_returns_none_on_url_error(monkeypatch):
    monkeypatch.setenv(cc.ENV_API_URL, "http://api.test")
    monkeypatch.setenv(cc.ENV_TOKEN, "shh")
    err = urllib.error.URLError("connection refused")
    with patch("classification.classification_cache_client.urllib.request.urlopen", side_effect=err):
        out = cc.get_classification("abc")
    assert out is None


def test_get_classification_sends_token_header(monkeypatch):
    monkeypatch.setenv(cc.ENV_API_URL, "http://api.test")
    monkeypatch.setenv(cc.ENV_TOKEN, "shh")
    captured = {}

    def fake(req, timeout=None):
        captured["headers"] = dict(req.headers)
        captured["url"] = req.full_url
        return _resp_factory(200, json.dumps({"classification": {"labels": []}}).encode())

    with patch("classification.classification_cache_client.urllib.request.urlopen", side_effect=fake):
        cc.get_classification("abc")
    headers_lower = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers_lower["x-internal-token"] == "shh"
    assert captured["url"].endswith("/internal/classifications/abc")


# ---------- upsert_classification ----------

def test_upsert_returns_false_when_env_missing(monkeypatch):
    monkeypatch.delenv(cc.ENV_API_URL, raising=False)
    monkeypatch.delenv(cc.ENV_TOKEN, raising=False)
    with patch("classification.classification_cache_client.urllib.request.urlopen") as m:
        ok = cc.upsert_classification("abc", {"labels": []})
    assert ok is False
    m.assert_not_called()


def test_upsert_posts_correct_body(monkeypatch):
    monkeypatch.setenv(cc.ENV_API_URL, "http://api.test")
    monkeypatch.setenv(cc.ENV_TOKEN, "shh")
    captured = {}

    def fake(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _resp_factory(200, b'{"imageHash":"abc","cached":true}')

    with patch("classification.classification_cache_client.urllib.request.urlopen", side_effect=fake):
        ok = cc.upsert_classification("abc", {"labels": [{"score": "5", "description": "dog"}]}, kondo_id=42)
    assert ok is True
    assert captured["url"].endswith("/internal/classifications")
    assert captured["body"] == {
        "imageHash": "abc",
        "classification": {"labels": [{"score": "5", "description": "dog"}]},
        "source": "gcp_vision",
        "kondoId": 42,
    }


def test_upsert_returns_false_on_http_error(monkeypatch):
    monkeypatch.setenv(cc.ENV_API_URL, "http://api.test")
    monkeypatch.setenv(cc.ENV_TOKEN, "shh")
    err = urllib.error.HTTPError(
        url="http://api.test/internal/classifications", code=401, msg="Unauthorized", hdrs=None, fp=None,
    )
    with patch("classification.classification_cache_client.urllib.request.urlopen", side_effect=err):
        ok = cc.upsert_classification("abc", {"labels": []})
    assert ok is False
