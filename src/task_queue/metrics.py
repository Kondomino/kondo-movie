"""
Lightweight Prometheus-style metrics for kondo-movie.

Stores counter + gauge values in Redis (so the worker process and api
process can both read/write the same numbers), formats `/metrics` as
plain Prometheus text exposition.

We deliberately do NOT depend on `prometheus_client` for v1 — adding
a new package means another lockfile regen, and the exposition format
is simple enough to roll by hand. If we ever need histogram buckets
or pull-mode push-gateway support, swapping in `prometheus_client` is
a single-file refactor (this module's public API is the seam).

Naming convention:
- counter keys: `kondo:metrics:<metric_name>{[label1=v1,...]}`
- gauges read at scrape time from Redis directly (no separate write
  path; we sample queue depth + heartbeat age inside the route).

Reset policy: never. Counters are monotonic since the deployment that
introduced this. Operator can `redis-cli DEL kondo:metrics:*` if they
need to zero them.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from redis.asyncio import Redis


METRICS_KEY_PREFIX = "kondo:metrics:"


def _build_counter_key(metric: str, labels: Optional[dict[str, str]] = None) -> str:
    """
    Encode a (metric, labels) pair as a Redis key. Labels are sorted by
    name so the same logical metric always produces the same key
    regardless of insertion order.
    """
    if not labels:
        return f"{METRICS_KEY_PREFIX}{metric}"
    label_str = ",".join(
        f"{k}={_sanitize_label_value(v)}"
        for k, v in sorted(labels.items())
        if v is not None
    )
    return f"{METRICS_KEY_PREFIX}{metric}{{{label_str}}}"


def _sanitize_label_value(value: Any) -> str:
    """
    Strip Prometheus-incompatible characters from label values. Newlines
    + double-quotes would break the exposition format.
    """
    text = str(value)
    return text.replace("\n", " ").replace('"', "'").replace("\\", "/")


async def incr_counter(
    redis: Redis,
    metric: str,
    labels: Optional[dict[str, str]] = None,
    by: int = 1,
) -> None:
    """
    Bump a counter atomically. Errors are swallowed — metrics writes
    must never fail the work they're observing.
    """
    try:
        await redis.incrby(_build_counter_key(metric, labels), by)
    except Exception:  # noqa: BLE001
        # Metrics writes never fail the caller. The /metrics scrape
        # will under-report briefly; that's acceptable.
        pass


async def add_to_counter(
    redis: Redis,
    metric: str,
    amount: float,
    labels: Optional[dict[str, str]] = None,
) -> None:
    """
    Add a float to a counter (e.g., duration sums). Uses INCRBYFLOAT.
    """
    try:
        await redis.incrbyfloat(_build_counter_key(metric, labels), amount)
    except Exception:  # noqa: BLE001
        pass


def _parse_counter_key(key: str) -> tuple[str, dict[str, str]]:
    """
    Reverse of _build_counter_key — extract metric + labels from a key
    so we can format the Prometheus exposition. Skips the prefix.

    `kondo:metrics:foo{a=1,b=2}` → ("foo", {"a": "1", "b": "2"})
    `kondo:metrics:foo`           → ("foo", {})
    """
    body = key[len(METRICS_KEY_PREFIX):] if key.startswith(METRICS_KEY_PREFIX) else key
    brace_idx = body.find("{")
    if brace_idx == -1:
        return body, {}
    metric = body[:brace_idx]
    labels_str = body[brace_idx + 1 : -1] if body.endswith("}") else body[brace_idx + 1 :]
    labels: dict[str, str] = {}
    for pair in labels_str.split(","):
        if not pair:
            continue
        k, _, v = pair.partition("=")
        if k:
            labels[k] = v
    return metric, labels


def _format_labels(labels: dict[str, str]) -> str:
    """Format a dict as Prometheus label syntax (or empty string)."""
    if not labels:
        return ""
    parts = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return "{" + parts + "}"


async def collect_counters(redis: Redis) -> list[tuple[str, dict[str, str], float]]:
    """
    Read all kondo:metrics:* keys and return parsed (metric, labels, value)
    tuples. Used by the /metrics route.
    """
    rows: list[tuple[str, dict[str, str], float]] = []
    async for raw_key in redis.scan_iter(
        match=f"{METRICS_KEY_PREFIX}*", count=200
    ):
        key = raw_key.decode() if isinstance(raw_key, (bytes, bytearray)) else raw_key
        try:
            raw_value = await redis.get(key)
            if raw_value is None:
                continue
            value = float(raw_value)
        except Exception:  # noqa: BLE001
            continue
        metric, labels = _parse_counter_key(key)
        rows.append((metric, labels, value))
    return rows


def render_prometheus_text(
    counters: Iterable[tuple[str, dict[str, str], float]],
    gauges: Optional[Iterable[tuple[str, dict[str, str], float]]] = None,
) -> str:
    """
    Format `(metric, labels, value)` tuples as Prometheus exposition.

    Groups by metric so each metric gets one HELP + TYPE line. The HELP
    text is generic since we don't carry it through Redis — this is
    operator-grade observability, not a customer-facing dashboard.
    """
    groups: dict[str, list[tuple[dict[str, str], float]]] = {}

    def _add(metric: str, labels: dict[str, str], value: float, kind_default: str) -> None:
        groups.setdefault(metric, []).append((labels, value))

    for metric, labels, value in counters:
        _add(metric, labels, value, "counter")

    lines: list[str] = []
    for metric in sorted(groups.keys()):
        lines.append(f"# HELP {metric} {metric}")
        # Heuristic: kondo_*_total is a counter; everything else is a gauge.
        kind = "counter" if metric.endswith("_total") else "gauge"
        lines.append(f"# TYPE {metric} {kind}")
        for labels, value in sorted(groups[metric], key=lambda lv: sorted(lv[0].items())):
            lines.append(f"{metric}{_format_labels(labels)} {value}")

    if gauges:
        for metric, labels, value in gauges:
            lines.append(f"# HELP {metric} {metric}")
            lines.append(f"# TYPE {metric} gauge")
            lines.append(f"{metric}{_format_labels(labels)} {value}")

    return "\n".join(lines) + "\n"
