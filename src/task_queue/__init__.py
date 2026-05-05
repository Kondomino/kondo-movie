"""
Task queue substrate for kondo-movie. arq-based, Redis as broker.

Phased rollout (see references/kondo/architecture/v2/video-render-reliability-plan.md):
  P0 (this PR) — bootstrap: Redis client factory, WorkerSettings shell, ping task.
  P3 — heartbeat helpers consumed by /readyz.
  P4 — render task; route still blocks awaiting result (transparent shim).
  P5 — route returns 202 immediately; webhook drives lifecycle.
  P6 — webhook delivery as a separate retry-aware queue.

Module name is `task_queue`, not `queue`, to avoid shadowing the
Python stdlib `queue` module on `sys.path` (tests prepend `src/`).
"""
