"""
OOM guard helpers for the render worker.

Two surfaces:

  - `FfmpegOomError` — raised when ffmpeg dies with exit code 137
    (SIGKILL by the OOM killer) or when the pre-render memory check
    refuses to start work on a worker that's already starving. The
    failure_classifier (P7) treats this as non-retryable: rerunning
    on the same machine just OOMs again.

  - `available_memory_bytes()` / `check_memory_pressure()` — read the
    Linux /proc/meminfo to estimate free memory before the render
    starts. If it's below a threshold, fail fast with FfmpegOomError
    so the operator gets a clean diagnostic rather than a mid-render
    SIGKILL with a partial output and a confused webhook.

The /proc/meminfo path is Linux-specific. On macOS/Windows (dev) the
read silently no-ops — workers only run on Fly's Linux containers in
prod, so the check is where it matters.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final


# Default minimum available memory before we'll start a render. perf-2x
# has 4GB total; ffmpeg + moviepy peak ~2.8GB on 1080p 60s renders, so
# 1GB free leaves a 0.2GB safety margin. Tunable via env for the rare
# operator who wants tighter limits in dev.
DEFAULT_MIN_AVAILABLE_BYTES: Final[int] = 1 * 1024 * 1024 * 1024  # 1 GB

_PROC_MEMINFO = Path("/proc/meminfo")


class FfmpegOomError(RuntimeError):
    """
    Raised when ffmpeg has been (or would be) killed by the OOM killer.

    Carriers `available_bytes` so the failure_classifier (P7) and the
    operator dashboard (P12) can surface "X MB free at fail time" for
    triage. None when the check couldn't run (non-Linux dev).
    """

    def __init__(self, message: str, *, available_bytes: int | None = None) -> None:
        super().__init__(message)
        self.available_bytes = available_bytes


def available_memory_bytes() -> int | None:
    """
    Best-effort read of the kernel's MemAvailable counter from
    /proc/meminfo. Returns the value in bytes, or None when the file
    can't be parsed (non-Linux, restricted FS, etc.).

    `MemAvailable` is the right field — it accounts for reclaimable
    page cache + slabs that the kernel can free under pressure, unlike
    `MemFree` which understates available memory dramatically on a
    busy host.
    """
    try:
        text = _PROC_MEMINFO.read_text()
    except OSError:
        return None

    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            # Format: `MemAvailable:    1234567 kB`
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024
            return None
    return None


def _min_available_bytes() -> int:
    """Resolve the threshold from env (operator override) or use the default."""
    raw = os.getenv("KONDO_MOVIE_MIN_AVAILABLE_BYTES")
    if raw and raw.isdigit():
        return int(raw)
    return DEFAULT_MIN_AVAILABLE_BYTES


def check_memory_pressure() -> None:
    """
    Pre-flight check before a render. Raises FfmpegOomError when
    available memory is below the threshold so the worker fails fast
    with a clean diagnostic rather than starting and getting OOM-killed
    mid-frame.

    Silent no-op when /proc/meminfo isn't readable (dev on macOS, etc.).
    Production runs on Linux containers where the file is always there.
    """
    available = available_memory_bytes()
    if available is None:
        return  # Non-Linux dev — no signal to act on.

    threshold = _min_available_bytes()
    if available < threshold:
        raise FfmpegOomError(
            f"Worker memory pressure: {available / (1024 * 1024):.0f} MB available, "
            f"need at least {threshold / (1024 * 1024):.0f} MB to start a render",
            available_bytes=available,
        )
