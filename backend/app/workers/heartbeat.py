"""Worker liveness heartbeat (V2 R2-1).

A cron job sets this key every 5 minutes with a TTL a bit longer than the
interval (400s) — so if the worker process dies, the key simply expires on
its own and /health/worker correctly reports unhealthy, with no need to
compare timestamps by hand.
"""

from datetime import datetime, timezone

HEARTBEAT_KEY = "spacepoint:worker:heartbeat"
HEARTBEAT_TTL_SECONDS = 400  # > the 300s (5 min) cron interval, with slack


async def heartbeat(ctx) -> None:
    redis = ctx["redis"]
    await redis.set(HEARTBEAT_KEY, datetime.now(timezone.utc).isoformat(), ex=HEARTBEAT_TTL_SECONDS)
