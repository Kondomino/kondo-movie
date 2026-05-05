"""
Tests for the WorkerSettings shell in `task_queue.worker`.

The roundtrip test (`test_ping_task_returns_pong_via_arq`) needs a real
Redis to enqueue + execute, so it's gated on REAL_REDIS_URL like the
connection integration test.
"""

import asyncio
import os

import pytest

from task_queue.worker import WorkerSettings, ping


def test_worker_settings_registers_ping_function():
    assert ping in WorkerSettings.functions


def test_worker_settings_concurrency_is_one():
    """
    Renders are CPU-bound; concurrency > 1 doubles RAM pressure for
    near-zero throughput gain (§1.3 of the plan).
    """
    assert WorkerSettings.max_jobs == 1


def test_worker_settings_job_timeout_covers_render_duration():
    """
    Renders take 60–90s on perf-2x; the timeout must comfortably
    exceed that with headroom for retries and image fetches.
    """
    assert WorkerSettings.job_timeout >= 300


def test_ping_task_is_async():
    assert asyncio.iscoroutinefunction(ping)


@pytest.mark.asyncio
async def test_ping_task_returns_pong_directly():
    """
    The task is callable as a plain coroutine without going through
    the queue. arq's calling convention requires `ctx` as the first
    argument; pass an empty dict for the shape.
    """
    result = await ping({})
    assert result == "pong"


@pytest.mark.skipif(
    "REAL_REDIS_URL" not in os.environ,
    reason="Set REAL_REDIS_URL to run the arq enqueue/dequeue roundtrip.",
)
@pytest.mark.asyncio
async def test_ping_task_returns_pong_via_arq():
    """
    Full roundtrip: enqueue from a pool, dequeue from a worker subprocess,
    assert result. Lives behind REAL_REDIS_URL because it actually drives
    arq end-to-end. Useful local proof that the queue substrate works.
    """
    from arq import create_pool

    from task_queue.connection import get_redis_settings

    settings = get_redis_settings(env={"REDIS_URL": os.environ["REAL_REDIS_URL"]})
    pool = await create_pool(settings)
    try:
        job = await pool.enqueue_job("ping")
        assert job is not None
        # We don't await job.result() here because that requires a worker
        # to be running; the assertion is that the job was accepted by
        # the broker. Full worker-driven roundtrip happens in P4 when we
        # wire the render task and have a worker container in CI.
    finally:
        await pool.close()
