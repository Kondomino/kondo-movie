"""
Tests for the Redis connection factory in `task_queue.connection`.

The integration test (`test_redis_client_pings_real_redis`) is skipped
unless REAL_REDIS_URL is set in the env — keeps `pytest` green on
machines without a local Redis. Set REAL_REDIS_URL=redis://localhost:6379/0
to exercise it during P0 development.
"""

import os

import pytest
from arq.connections import RedisSettings

from task_queue.connection import (
    DEFAULT_REDIS_URL,
    get_redis_settings,
    get_redis_url,
)


def test_redis_url_uses_default_when_env_missing():
    assert get_redis_url(env={}) == DEFAULT_REDIS_URL


def test_redis_url_uses_env_value_when_set():
    custom = "redis://:s3cret@redis.example.com:6380/2"
    assert get_redis_url(env={"REDIS_URL": custom}) == custom


def test_redis_settings_parses_default_dsn():
    settings = get_redis_settings(env={})
    assert isinstance(settings, RedisSettings)
    # arq's RedisSettings exposes parsed components; we don't pin the
    # exact attribute names because they shift between minor versions —
    # just assert that parsing succeeded and the host is recognisable.
    assert "localhost" in repr(settings) or settings.host == "localhost"


def test_redis_settings_parses_custom_dsn():
    settings = get_redis_settings(env={"REDIS_URL": "redis://redis.example.com:6380/3"})
    assert isinstance(settings, RedisSettings)
    assert settings.host == "redis.example.com"
    assert settings.port == 6380
    assert settings.database == 3


@pytest.mark.skipif(
    "REAL_REDIS_URL" not in os.environ,
    reason="Set REAL_REDIS_URL to run the integration smoke against a real Redis.",
)
@pytest.mark.asyncio
async def test_redis_client_pings_real_redis():
    """
    End-to-end: settings → arq pool → PING → PONG. Skipped on CI by
    default; meant for local verification while we're still bringing
    the queue layer up.
    """
    from arq import create_pool

    settings = get_redis_settings(env={"REDIS_URL": os.environ["REAL_REDIS_URL"]})
    pool = await create_pool(settings)
    try:
        result = await pool.ping()
        assert result is True or result == b"PONG" or result == "PONG"
    finally:
        await pool.close()
