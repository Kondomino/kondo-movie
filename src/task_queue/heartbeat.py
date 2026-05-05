"""
Heartbeat helpers consumed by `/readyz` and (in P4) by the render
worker.

Contract:
- Each worker process owns a key `kondo:worker:<machine_id>:heartbeat`
  and writes the current ISO8601 UTC timestamp every HEARTBEAT_PERIOD
  seconds. The key carries a TTL of HEARTBEAT_TTL so a dead worker's
  key auto-expires from Redis.
- `/readyz` does NOT enumerate worker machines; it scans for any keys
  matching `kondo:worker:*:heartbeat` and returns the freshest one.
  If the freshest is older than HEARTBEAT_STALE_AFTER seconds, the
  service reports `degraded` (status=503).
- P3 (this PR) ships only the READ side — `read_latest_heartbeat`. The
  WRITE side (`write_heartbeat`) lands here too as the contract, but
  no caller invokes it yet. P4 (worker process) wires it in.

This module is pure-async + Redis-only. No FastAPI imports, no DB,
no external services. Fits the architecture-bar bar: small, testable,
swappable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis

# Cadence + TTL constants. Worker writes every HEARTBEAT_PERIOD; key
# expires after HEARTBEAT_TTL with no refresh; `/readyz` flags
# degraded after HEARTBEAT_STALE_AFTER. The hierarchy must be
# WRITE_PERIOD < STALE_AFTER < TTL so a brief network blip doesn't
# falsely trip the readiness probe.
HEARTBEAT_PERIOD_SECONDS = 15
HEARTBEAT_STALE_AFTER_SECONDS = 30
HEARTBEAT_TTL_SECONDS = 60

WORKER_HEARTBEAT_KEY_PREFIX = "kondo:worker:"
WORKER_HEARTBEAT_KEY_SUFFIX = ":heartbeat"
WORKER_HEARTBEAT_KEY_PATTERN = (
    f"{WORKER_HEARTBEAT_KEY_PREFIX}*{WORKER_HEARTBEAT_KEY_SUFFIX}"
)


def _heartbeat_key(machine_id: str) -> str:
    return f"{WORKER_HEARTBEAT_KEY_PREFIX}{machine_id}{WORKER_HEARTBEAT_KEY_SUFFIX}"


async def write_heartbeat(redis: Redis, machine_id: str) -> None:
    """
    Worker-side: stamp the current UTC time on this machine's heartbeat
    key with HEARTBEAT_TTL TTL. P4 calls this from the arq worker on
    its periodic loop. Not invoked by anything yet in P3.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    await redis.set(
        _heartbeat_key(machine_id),
        now_iso,
        ex=HEARTBEAT_TTL_SECONDS,
    )


async def read_latest_heartbeat(redis: Redis) -> Optional[datetime]:
    """
    `/readyz`-side: scan for any worker heartbeat key, parse each
    timestamp, return the most recent. None when no heartbeat keys
    exist (e.g. no workers running yet — the P3 baseline state).

    Uses SCAN, not KEYS, to avoid blocking Redis on large keyspaces.
    Cap is conservative: at v1 we expect 1-2 worker machines, so a
    SCAN window of 100 captures everything in a single round-trip.
    """
    latest: Optional[datetime] = None

    async for key in redis.scan_iter(
        match=WORKER_HEARTBEAT_KEY_PATTERN, count=100
    ):
        raw = await redis.get(key)
        if raw is None:
            # Key was evicted between SCAN and GET — skip silently.
            continue
        try:
            ts = datetime.fromisoformat(
                raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
            )
        except (ValueError, AttributeError):
            # A non-timestamp value got into the heartbeat key by
            # mistake (manual debug, schema drift). Don't crash readyz
            # on it; just ignore.
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if latest is None or ts > latest:
            latest = ts

    return latest


def heartbeat_age_seconds(ts: Optional[datetime]) -> Optional[float]:
    """
    Convenience for `/readyz` reporting. Returns the integer-second
    age of `ts` from now. None when ts is None (no heartbeat seen).
    """
    if ts is None:
        return None
    now = datetime.now(timezone.utc)
    return max((now - ts).total_seconds(), 0.0)


def is_heartbeat_stale(ts: Optional[datetime]) -> bool:
    """True when the freshest heartbeat is missing or too old."""
    age = heartbeat_age_seconds(ts)
    if age is None:
        return True
    return age > HEARTBEAT_STALE_AFTER_SECONDS
