"""
arq WorkerSettings for the kondo-movie render worker.

P0 shipped a no-op `ping`. P4 adds:
  - the real `render_movie` task (see task_queue.tasks)
  - a continuous heartbeat loop that writes `kondo:worker:<id>:heartbeat`
    every HEARTBEAT_PERIOD_SECONDS, so `/readyz` knows the worker is
    alive even mid-render.

Run locally with:
    poetry run arq task_queue.worker.WorkerSettings

In production the worker is a second Fly process per fly.toml
[[processes]] block, distinguished from the API process by entrypoint.
The Fly machine ID becomes the heartbeat key suffix.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from arq.connections import RedisSettings

from logger import logger
from task_queue.connection import get_redis_settings
from task_queue.heartbeat import (
    HEARTBEAT_PERIOD_SECONDS,
    write_heartbeat,
)
from task_queue.tasks import deliver_webhook, render_movie


# Module-level handle to the heartbeat loop task. Stored here so
# `on_shutdown` can cancel it cleanly. Single worker process per
# machine = single task, no contention.
_heartbeat_task: asyncio.Task[None] | None = None


def _machine_id() -> str:
    """
    Identify this worker for heartbeat keying. Fly sets FLY_MACHINE_ID
    in the runtime env. Local dev falls through to a stable "local"
    string so multiple local restarts share the same heartbeat slot.
    """
    return os.getenv("FLY_MACHINE_ID") or os.getenv("HOSTNAME") or "local"


async def _heartbeat_loop(redis: Any, machine_id: str) -> None:
    """
    Continuous heartbeat writer. Runs as a top-level asyncio task on
    the worker's event loop. Survives transient Redis errors — a single
    failed write is logged at warning, the loop sleeps then tries
    again. Cancellation lands cleanly via on_shutdown.
    """
    while True:
        try:
            await write_heartbeat(redis, machine_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[VIDEO-WORKER] heartbeat write failed (machine={machine_id}): "
                f"{type(exc).__name__}: {exc}"
            )
        try:
            await asyncio.sleep(HEARTBEAT_PERIOD_SECONDS)
        except asyncio.CancelledError:
            return


async def on_startup(ctx: dict[str, Any]) -> None:
    """Spawn the heartbeat loop. arq exposes the Redis pool as ctx['redis']."""
    global _heartbeat_task
    machine_id = _machine_id()
    logger.info(
        f"[VIDEO-WORKER] starting heartbeat loop machine={machine_id} "
        f"period={HEARTBEAT_PERIOD_SECONDS}s"
    )
    _heartbeat_task = asyncio.create_task(
        _heartbeat_loop(ctx["redis"], machine_id),
        name="kondo-worker-heartbeat",
    )


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """Cancel the heartbeat loop so the worker exits cleanly."""
    global _heartbeat_task
    if _heartbeat_task is None:
        return
    _heartbeat_task.cancel()
    try:
        await _heartbeat_task
    except asyncio.CancelledError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            f"[VIDEO-WORKER] heartbeat loop exited unexpectedly: "
            f"{type(exc).__name__}: {exc}"
        )
    _heartbeat_task = None


async def ping(ctx: dict[str, Any]) -> str:
    """Smoke-test task from P0. Kept for local debugging."""
    return "pong"


class WorkerSettings:
    """
    arq picks up these class-level attributes when started via
    `arq task_queue.worker.WorkerSettings`.

    Concurrency is locked to 1 because renders are CPU-bound on ffmpeg
    and saturate perf-2x (plan §1.3). Multiple concurrent renders on
    one machine doesn't help throughput and doubles RAM pressure.
    """

    functions = [ping, render_movie, deliver_webhook]
    redis_settings: RedisSettings = get_redis_settings()
    # max_jobs governs concurrent renders. deliver_webhook is short-lived
    # (a single HTTP POST) and shares the same worker; in practice the
    # bottleneck is always the render so this is fine.
    max_jobs: int = 1
    job_timeout: int = 600  # 10 min — renders are 60-90s on perf-2x
    keep_result: int = 3600  # 1h — webhook is the source of truth
    on_startup = on_startup
    on_shutdown = on_shutdown
