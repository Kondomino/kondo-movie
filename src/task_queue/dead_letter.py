"""
Dead-letter helpers for webhooks that exhaust all retries.

Failed deliveries land in a Redis ZSET keyed `kondo:webhook:dead` with
score=epoch-seconds. Members are JSON-encoded payload+metadata so an
operator can inspect via `redis-cli ZRANGE`. The ZSET key gets a
DEAD_LETTER_TTL_SECONDS expiry on every write so old entries age out
without explicit cleanup.

Retrieval / replay UI is out of scope for v1 (per plan §P12 — operator
dashboard lands later). For now the alert path on dead-letter is
Telegram via the existing alerts substrate (P12).
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from redis.asyncio import Redis

from logger import logger


DEAD_LETTER_KEY = "kondo:webhook:dead"
# 7 days. Keeps recent dead-letters around for ad-hoc inspection
# without unbounded growth. TTL refreshed on every write.
DEAD_LETTER_TTL_SECONDS = 7 * 24 * 60 * 60


async def push_dead_letter(
    redis: Redis,
    webhook_url: str,
    payload: dict[str, Any],
    *,
    reason: str,
    attempts: int,
    job_id: Optional[str] = None,
) -> None:
    """
    Record a permanently-failed webhook delivery for later inspection.

    Members are JSON blobs containing `webhook_url`, `payload`, `reason`,
    `attempts`, `job_id`, and `dead_at` (epoch seconds). Score = dead_at
    so ZRANGEBYSCORE can target a time window when the operator triages.

    Idempotent under repeat calls — Redis ZADD treats a duplicate member
    as a score update (move-to-now). Exceptions are logged and swallowed:
    the worker has already exhausted retries and we don't want a Redis
    blip to also lose the diagnostic.
    """
    now = int(time.time())
    record = {
        "webhook_url": webhook_url,
        "payload": payload,
        "reason": reason,
        "attempts": attempts,
        "job_id": job_id,
        "dead_at": now,
    }
    try:
        member = json.dumps(record, sort_keys=True, default=str)
        await redis.zadd(DEAD_LETTER_KEY, {member: now})
        await redis.expire(DEAD_LETTER_KEY, DEAD_LETTER_TTL_SECONDS)
        logger.error(
            f"[VIDEO-WEBHOOK] dead-lettered job_id={job_id} "
            f"reason={reason} attempts={attempts} url={webhook_url}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            f"[VIDEO-WEBHOOK] dead-letter persist FAILED job_id={job_id} "
            f"reason={reason} — and now also lost the diagnostic: "
            f"{type(exc).__name__}: {exc}"
        )
