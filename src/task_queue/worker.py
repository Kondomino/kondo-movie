"""
arq WorkerSettings for the kondo-movie render worker.

Phase 0 ships a single no-op `ping` task — proves the wiring (worker
process can import settings, connect to Redis, dequeue a job, return a
result) without yet touching the render pipeline. P4 adds the real
`render_movie` task that calls into MovieActionsHandler.

Run locally with:
  poetry run arq task_queue.worker.WorkerSettings

In production (P4+) the worker is a second Fly process per fly.toml
[[processes]] block, distinguished from the API process by entrypoint.
"""

from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from task_queue.connection import get_redis_settings


async def ping(ctx: dict[str, Any]) -> str:
    """
    Smoke-test task. Useful for proving the queue end-to-end in dev
    and as a P3 readiness probe target. Not called from production
    code paths once real tasks land in P4+.
    """
    return "pong"


class WorkerSettings:
    """
    arq picks up these class-level attributes when started via
    `arq task_queue.worker.WorkerSettings`. Concurrency is locked to 1
    because renders are CPU-bound on ffmpeg and saturate perf-2x; see
    plan §1.3.
    """

    functions = [ping]
    redis_settings: RedisSettings = get_redis_settings()
    max_jobs: int = 1
    job_timeout: int = 600  # 10 min — renders are 60-90s on perf-2x
    keep_result: int = 3600  # 1h — webhook is the source of truth, this is debug-aid only
