"""
kondo-movie logger setup.

Two output modes:
  - default (dev): loguru's pretty multi-color sink to stdout.
  - LOG_FORMAT=json (prod-deploy + Axiom): one JSON object per line on
    stdout. Loguru's `serialize=True` produces a verbose record; we
    use a custom serialiser to emit only the fields ops actually
    consume. Stable schema for APL queries.

Operators reading logs:
  - `jq 'select(.engine_job_id == "X")'` — full timeline of one render
  - `jq 'select(.tag | startswith("VIDEO-WEBHOOK"))'` — webhook side
  - `jq 'select(.level == "ERROR")'` — error-only feed

The tag lives at the start of each message (`[VIDEO-WORKER] ...`) and
is also surfaced as a top-level `tag` field for direct filter grammar
in APL. Pre-existing call sites don't need to change — the format
extracts the tag from the message.
"""

import json
import logging
import os
import re
import sys
from typing import Any

from dotenv import load_dotenv
from google.cloud import logging as g_logging
from google.cloud.logging.handlers import CloudLoggingHandler
from loguru import logger

from config.config import settings


load_dotenv()


_TAG_REGEX = re.compile(r"\[(?P<tag>[A-Z][A-Z0-9_-]*)\]")


def _extract_tag(message: str) -> str | None:
    """
    Pull the leading bracketed tag out of a log message
    (e.g. `[VIDEO-WORKER] render started ...` → `VIDEO-WORKER`).
    Returns None when no tag is present so the JSON has a `null`
    rather than a misleading inferred value.
    """
    match = _TAG_REGEX.search(message)
    return match.group("tag") if match else None


def _json_sink(message: Any) -> None:
    """
    Custom loguru sink for JSON output. Emits one compact object per
    log call, stable field order. Stdout-only — Axiom shipper picks
    it up off the Fly machine logs.
    """
    record = message.record
    payload: dict[str, Any] = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "msg": record["message"],
        "tag": _extract_tag(record["message"]),
        "logger": record["name"],
    }
    # Anything callers passed via logger.bind() lands in `extra`.
    extras = record.get("extra") or {}
    if extras:
        # Promote known fields to top-level for easier APL access.
        for known in (
            "engine_job_id",
            "kondo_id",
            "agent_id",
            "phase",
            "attempt",
            "duration_ms",
        ):
            if known in extras:
                payload[known] = extras[known]
        # Anything else ends up under `extra` to keep the top-level
        # shape stable.
        residual = {k: v for k, v in extras.items() if k not in payload}
        if residual:
            payload["extra"] = residual

    if record["exception"] is not None:
        # Stringify; ops dashboards are usually fine with a flat field.
        payload["exception"] = str(record["exception"])

    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


class SingletonLogger:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.setup_logger()
        return cls._instance

    def setup_logger(self):
        # Configure Loguru
        logger.remove()  # Remove default handler

        log_level = os.getenv("LOG_LEVEL") or "INFO"
        log_format = (os.getenv("LOG_FORMAT") or "").lower()
        deployment = os.getenv("DEPLOYMENT")

        if deployment == "CLOUD":
            g_client = g_logging.Client(project=settings.GCP.PROJECT_ID)
            g_client.setup_logging(log_level=logging.WARNING)
            g_logging_handler = CloudLoggingHandler(client=g_client)
            logger.add(sink=g_logging_handler, level=log_level)
        elif log_format == "json":
            # Production / Fly deploy: every line is a JSON object so
            # the Axiom log shipper can index fields directly.
            logger.add(sink=_json_sink, level=log_level, format="{message}")
        else:
            # Dev: loguru's default colorised pretty output.
            logger.add(sink=sys.stdout, level=log_level)

    def get_logger(self):
        return logger


logger = SingletonLogger().get_logger()
