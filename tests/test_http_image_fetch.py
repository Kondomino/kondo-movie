"""
Pin the http(s) image-fetch helpers used by `_fetch_images` when kondos-api
sends public R2 / DO Spaces / S3-compat URLs in `ordered_images`.
Imports the standalone module to skip the DB-bound side effects of
`movie_actions`.
"""

from unittest.mock import patch, MagicMock

import pytest

from movie_maker.image_fetch import (
    download_http_image,
    suffix_from_url,
    is_http_url,
)


def test_suffix_from_url_strips_query_and_fragment():
    assert suffix_from_url("https://cdn.example.com/foo/img1.jpg") == ".jpg"
    assert suffix_from_url("https://cdn.example.com/foo/img2.png?x=1&y=2") == ".png"
    assert (
        suffix_from_url("https://cdn.example.com/foo/img3.webp?X-Amz-Signature=abc#anchor")
        == ".webp"
    )


def test_suffix_from_url_defaults_to_jpg_when_unknown():
    assert suffix_from_url("https://cdn.example.com/foo/img-no-ext") == ".jpg"
    assert suffix_from_url("https://cdn.example.com/foo/") == ".jpg"


def test_is_http_url():
    assert is_http_url("http://example.com/x.jpg") is True
    assert is_http_url("https://example.com/x.jpg") is True
    assert is_http_url("HTTPS://EXAMPLE.COM/X.JPG") is True
    assert is_http_url("gs://bucket/x.jpg") is False
    assert is_http_url("s3://bucket/x.jpg") is False
    assert is_http_url("/local/path/x.jpg") is False


def test_download_http_image_streams_chunks_to_disk(tmp_path):
    dest = tmp_path / "downloaded.jpg"
    fake_chunks = [b"hello", b"world", b""]

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.iter_content = MagicMock(return_value=iter(fake_chunks))

    with patch("movie_maker.image_fetch.requests.get", return_value=fake_response) as get:
        download_http_image("https://cdn.example.com/p.jpg", str(dest))

    get.assert_called_once()
    _, kwargs = get.call_args
    assert kwargs["stream"] is True
    assert kwargs["timeout"] > 0

    assert dest.read_bytes() == b"helloworld"


def test_download_http_image_raises_on_non_2xx(tmp_path):
    dest = tmp_path / "out.jpg"
    fake_response = MagicMock()
    fake_response.status_code = 404
    fake_response.iter_content = MagicMock(return_value=iter([]))

    with patch("movie_maker.image_fetch.requests.get", return_value=fake_response):
        with pytest.raises(ValueError, match="HTTP 404"):
            download_http_image("https://cdn.example.com/missing.jpg", str(dest))


def test_download_http_image_skips_empty_chunks(tmp_path):
    dest = tmp_path / "out.jpg"
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.iter_content = MagicMock(return_value=iter([b"", b"abc", b"", b"def"]))

    with patch("movie_maker.image_fetch.requests.get", return_value=fake_response):
        download_http_image("https://cdn.example.com/p.jpg", str(dest))

    assert dest.read_bytes() == b"abcdef"
