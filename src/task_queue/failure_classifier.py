"""
Pure-function classifier for render failures.

Inspects either an exception or a `result.reason` string from
MovieActionsHandler and tells the caller:
  - which failure class it is (drives the metrics label in P9)
  - whether to retry
  - the per-class max attempts

Heuristics-based on type names + message substrings. Future P11 (OOM
guard) will introduce typed exceptions for ffmpeg specifically; until
then the heuristics cover the common shapes we've seen in prod.

Per the §2.4 retry table of the reliability plan:
  | Failure                        | Retryable? | Max attempts |
  | image fetch 5xx / timeout      | yes        | 3            |
  | image fetch 4xx                | no         | 1            |
  | ffmpeg crash (non-OOM)         | yes        | 2            |
  | ffmpeg OOM (exit 137)          | NO         | 1            |
  | r2 upload 5xx / timeout        | yes        | 5            |
  | r2 upload 4xx                  | no         | 1            |
  | elevenlabs 429                 | yes        | 5            |  (NARRATION_ACTIVE=false)
  | elevenlabs 5xx                 | yes        | 3            |
  | assemblyai timeout             | yes        | 2            |  (off in v1)
  | catch-all unknown              | yes        | 2            |
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional


# Public failure-class taxonomy. Used as the failure_class metric label
# in P9 — keep stable across versions; renaming = histogram churn.
FAILURE_CLASS_OOM: Final[str] = "oom"
FAILURE_CLASS_FFMPEG: Final[str] = "ffmpeg"
FAILURE_CLASS_R2_UPLOAD: Final[str] = "r2_upload"
FAILURE_CLASS_IMAGE_FETCH: Final[str] = "image_fetch"
FAILURE_CLASS_ELEVENLABS: Final[str] = "elevenlabs"
FAILURE_CLASS_ASSEMBLYAI: Final[str] = "assemblyai"
FAILURE_CLASS_UNKNOWN: Final[str] = "unknown"


@dataclass(frozen=True)
class FailureClassification:
    failure_class: str
    retryable: bool
    max_tries: int

    def has_attempts_left(self, current_try: int) -> bool:
        """True if the caller should retry given current_try is 1-indexed."""
        return self.retryable and current_try < self.max_tries


def _has_http_status(exc: BaseException) -> Optional[int]:
    """
    Best-effort HTTP-status extraction for libraries we touch:
    - urllib.error.HTTPError exposes `.code`
    - boto3 ClientError carries it inside response['ResponseMetadata']
    - requests' HTTPError uses `.response.status_code`
    Returns None when no status is recoverable.
    """
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    response = getattr(exc, "response", None)
    if response is not None:
        meta = getattr(response, "get", None)
        if callable(meta):
            md = response.get("ResponseMetadata") if hasattr(response, "get") else None
            if isinstance(md, dict):
                status = md.get("HTTPStatusCode")
                if isinstance(status, int):
                    return status
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code
    return None


def classify_failure(
    exc: Optional[BaseException] = None,
    reason: Optional[str] = None,
) -> FailureClassification:
    """
    Categorise a render failure. Pass `exc` when a Python exception
    bubbled up; pass `reason` when MovieActionsHandler returned a
    `FAILURE` action_response with a textual reason. Either or both.
    """
    type_name = type(exc).__name__ if exc is not None else ""
    haystacks: list[str] = []
    if exc is not None:
        haystacks.append(f"{type_name}: {exc}".lower())
    if reason:
        haystacks.append(reason.lower())
    text = " | ".join(haystacks)

    # ---- OOM (highest-priority signal — drop fast, no retry) ----
    if exc is not None and isinstance(exc, MemoryError):
        return FailureClassification(FAILURE_CLASS_OOM, retryable=False, max_tries=1)
    # ffmpeg OOM-by-signal: kernel sends SIGKILL (exit 137) when the
    # OOM killer fires. Also catch generic "killed" / "out of memory" /
    # "memory" + "exhaust" markers.
    if (
        "exit code 137" in text
        or "exit status 137" in text
        or "signal 9" in text
        or "sigkill" in text
        or "out of memory" in text
        or ("oom" in text and "killer" in text)
    ):
        return FailureClassification(FAILURE_CLASS_OOM, retryable=False, max_tries=1)

    # ---- Image fetch ----
    # urllib.error.HTTPError when downloading kondo media. 4xx ⇒ bad
    # input, fail fast; 5xx / timeout ⇒ retry.
    if "urlopen" in text or "url_fetch" in text or "image" in text and "fetch" in text:
        status = _has_http_status(exc) if exc is not None else None
        if status and 400 <= status < 500:
            return FailureClassification(FAILURE_CLASS_IMAGE_FETCH, retryable=False, max_tries=1)
        return FailureClassification(FAILURE_CLASS_IMAGE_FETCH, retryable=True, max_tries=3)
    # urllib HTTPError without "image" hint — still treat as image fetch
    # since that's the main HTTP touchpoint pre-narration.
    if exc is not None and type_name == "HTTPError":
        status = _has_http_status(exc)
        if status and 400 <= status < 500:
            return FailureClassification(FAILURE_CLASS_IMAGE_FETCH, retryable=False, max_tries=1)
        return FailureClassification(FAILURE_CLASS_IMAGE_FETCH, retryable=True, max_tries=3)

    # ---- R2 upload ----
    # boto3 ClientError surfaces with .response['ResponseMetadata'].
    # Also catch by class-name + message hints.
    if (
        "r2" in text
        or "cloudflare" in text
        or "s3" in text
        or "boto" in text
        or "clienterror" in type_name.lower()
        or "uploadfailed" in type_name.lower()
    ):
        status = _has_http_status(exc) if exc is not None else None
        if status and 400 <= status < 500:
            return FailureClassification(FAILURE_CLASS_R2_UPLOAD, retryable=False, max_tries=1)
        return FailureClassification(FAILURE_CLASS_R2_UPLOAD, retryable=True, max_tries=5)

    # ---- TTS / captions (off in v1, but pre-position the contract) ----
    if "elevenlabs" in text:
        # 429 is rate-limit, retryable up to 5; everything else 3.
        if "429" in text or "rate" in text and "limit" in text:
            return FailureClassification(FAILURE_CLASS_ELEVENLABS, retryable=True, max_tries=5)
        return FailureClassification(FAILURE_CLASS_ELEVENLABS, retryable=True, max_tries=3)
    if "assemblyai" in text:
        return FailureClassification(FAILURE_CLASS_ASSEMBLYAI, retryable=True, max_tries=2)

    # ---- ffmpeg (non-OOM crash) — moviepy wraps it; subprocess too ----
    if (
        "ffmpeg" in text
        or "moviepy" in text
        or "calledprocesserror" in type_name.lower()
        or "subprocess" in type_name.lower()
    ):
        return FailureClassification(FAILURE_CLASS_FFMPEG, retryable=True, max_tries=2)

    # ---- Catch-all ----
    return FailureClassification(FAILURE_CLASS_UNKNOWN, retryable=True, max_tries=2)


# Backoff between render retries (seconds, indexed by job_try-1).
# Renders are 60-90s themselves, so backoff is shorter than webhook —
# we want quick recovery on transient blips, not hours-long waits.
RENDER_RETRY_BACKOFF_SECONDS: Final[list[int]] = [30, 60, 120, 300, 600]


def backoff_for_attempt(job_try: int) -> int:
    """Pick the right defer for the current attempt (1-indexed)."""
    idx = max(job_try - 1, 0)
    idx = min(idx, len(RENDER_RETRY_BACKOFF_SECONDS) - 1)
    return RENDER_RETRY_BACKOFF_SECONDS[idx]
