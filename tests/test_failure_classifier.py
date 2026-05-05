"""
P7: unit tests for the failure classifier.

The classifier is a pure function — no fixtures, no Redis. Tests pin
the §2.4 retry-table contract: which inputs map to which class +
retryable + max_tries.
"""

from __future__ import annotations

import urllib.error

import pytest

import os
_R2_DUMMIES = {
    "CLOUDFLARE_R2_KEY_ID": "test-r2-key-id",
    "CLOUDFLARE_R2_ACCESS_KEY": "test-r2-access-key",
    "CLOUDFLARE_R2_ENDPOINT": "https://test-r2.example.com",
}
for _k, _v in _R2_DUMMIES.items():
    os.environ.setdefault(_k, _v)

from task_queue.failure_classifier import (  # noqa: E402
    FAILURE_CLASS_ASSEMBLYAI,
    FAILURE_CLASS_ELEVENLABS,
    FAILURE_CLASS_FFMPEG,
    FAILURE_CLASS_IMAGE_FETCH,
    FAILURE_CLASS_OOM,
    FAILURE_CLASS_R2_UPLOAD,
    FAILURE_CLASS_UNKNOWN,
    RENDER_RETRY_BACKOFF_SECONDS,
    backoff_for_attempt,
    classify_failure,
)


# ---- OOM ----

def test_classifies_memory_error_as_oom():
    c = classify_failure(MemoryError("out of memory"))
    assert c.failure_class == FAILURE_CLASS_OOM
    assert c.retryable is False
    assert c.max_tries == 1


def test_classifies_ffmpeg_exit_137_as_oom():
    """ffmpeg killed by SIGKILL (typical OOM-killer behavior) — exit 137."""
    c = classify_failure(reason="ffmpeg failed: exit code 137")
    assert c.failure_class == FAILURE_CLASS_OOM
    assert c.retryable is False


def test_classifies_sigkill_text_as_oom():
    c = classify_failure(reason="render aborted: signal 9 (SIGKILL)")
    assert c.failure_class == FAILURE_CLASS_OOM


# ---- ffmpeg (non-OOM) ----

def test_classifies_ffmpeg_crash_as_retryable_2_tries():
    c = classify_failure(reason="moviepy ffmpeg subprocess returned exit 1")
    assert c.failure_class == FAILURE_CLASS_FFMPEG
    assert c.retryable is True
    assert c.max_tries == 2


# ---- Image fetch ----

def test_classifies_image_404_as_fail_fast():
    """4xx on image download = bad input, no retry."""
    err = urllib.error.HTTPError(
        url="https://cdn/x.jpg", code=404, msg="Not Found", hdrs=None, fp=None
    )
    c = classify_failure(err)
    assert c.failure_class == FAILURE_CLASS_IMAGE_FETCH
    assert c.retryable is False
    assert c.max_tries == 1


def test_classifies_image_503_as_retryable_3_tries():
    err = urllib.error.HTTPError(
        url="https://cdn/x.jpg", code=503, msg="Service Unavailable", hdrs=None, fp=None
    )
    c = classify_failure(err)
    assert c.failure_class == FAILURE_CLASS_IMAGE_FETCH
    assert c.retryable is True
    assert c.max_tries == 3


# ---- R2 upload ----

def test_classifies_r2_5xx_as_retryable_5_max():
    """boto3-style ClientError shape with 503 → R2, retry up to 5."""

    class _FakeClientError(Exception):
        pass

    err = _FakeClientError("R2 upload to kondo-properties failed")
    err.response = {"ResponseMetadata": {"HTTPStatusCode": 503}}
    c = classify_failure(err)
    assert c.failure_class == FAILURE_CLASS_R2_UPLOAD
    assert c.retryable is True
    assert c.max_tries == 5


def test_classifies_r2_403_as_fail_fast():
    """4xx on R2 = config issue (bad key, bucket policy), no retry."""

    class _FakeClientError(Exception):
        pass

    err = _FakeClientError("R2 access denied")
    err.response = {"ResponseMetadata": {"HTTPStatusCode": 403}}
    c = classify_failure(err)
    assert c.failure_class == FAILURE_CLASS_R2_UPLOAD
    assert c.retryable is False


# ---- TTS / captions (placeholder paths — off in v1) ----

def test_classifies_elevenlabs_429_as_retryable_5():
    c = classify_failure(reason="ElevenLabs 429: rate limit hit")
    assert c.failure_class == FAILURE_CLASS_ELEVENLABS
    assert c.max_tries == 5


def test_classifies_elevenlabs_500_as_retryable_3():
    c = classify_failure(reason="ElevenLabs 500: internal server error")
    assert c.failure_class == FAILURE_CLASS_ELEVENLABS
    assert c.max_tries == 3


def test_classifies_assemblyai_timeout_as_retryable_2():
    c = classify_failure(reason="AssemblyAI request timed out")
    assert c.failure_class == FAILURE_CLASS_ASSEMBLYAI
    assert c.max_tries == 2


# ---- Catch-all ----

def test_unknown_error_gets_2_max_tries():
    c = classify_failure(RuntimeError("something weird happened"))
    assert c.failure_class == FAILURE_CLASS_UNKNOWN
    assert c.retryable is True
    assert c.max_tries == 2


# ---- has_attempts_left ----

def test_has_attempts_left_on_first_try_for_retryable():
    c = classify_failure(RuntimeError("transient"))
    assert c.has_attempts_left(1) is True


def test_no_attempts_left_when_exhausted():
    c = classify_failure(RuntimeError("transient"))  # max_tries=2
    assert c.has_attempts_left(2) is False


def test_no_attempts_left_when_non_retryable():
    c = classify_failure(MemoryError())
    assert c.has_attempts_left(1) is False


# ---- backoff_for_attempt ----

def test_backoff_first_attempt_is_first_in_schedule():
    assert backoff_for_attempt(1) == RENDER_RETRY_BACKOFF_SECONDS[0]


def test_backoff_clamps_to_last_when_exceeding_schedule():
    """Even if job_try goes beyond the schedule, return the last value."""
    last = RENDER_RETRY_BACKOFF_SECONDS[-1]
    assert backoff_for_attempt(99) == last
