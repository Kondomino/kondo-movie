"""
Redis connection factory for the arq queue.

Reads `REDIS_URL` from the environment. Format (per arq docs):
  redis://[:password@]host:port/db

Single source of truth for both the API process (which enqueues
jobs) and the worker process (which consumes them). Centralising
the parsing here keeps WorkerSettings + main.py from each rolling
their own DSN handling.
"""

from __future__ import annotations

import os
from typing import Optional

from arq.connections import RedisSettings


# Default points at a local docker-compose Redis on the standard port,
# matching the dev compose stack. Production sets REDIS_URL to the Redis
# Cloud DSN via Fly secret.
DEFAULT_REDIS_URL = "redis://localhost:6379/0"


def get_redis_url(env: Optional[dict[str, str]] = None) -> str:
    """
    Resolve the Redis DSN. Accepts an optional env mapping for tests
    so we don't have to monkeypatch `os.environ` everywhere.
    """
    source = env if env is not None else os.environ
    return source.get("REDIS_URL", DEFAULT_REDIS_URL)


def get_redis_settings(env: Optional[dict[str, str]] = None) -> RedisSettings:
    """
    Build the arq RedisSettings used by both the enqueue side and the
    worker side. Called at import time from worker.py and on demand
    from the API process when it needs to push a job.
    """
    return RedisSettings.from_dsn(get_redis_url(env))
