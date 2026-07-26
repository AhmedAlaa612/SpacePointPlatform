"""ARQ/Redis connection settings (V2 R2-1).

Shared by both sides: the worker process (app/workers/main.py) consumes jobs
from this Redis instance, and the web app enqueues jobs into it (see
app/main.py's lifespan, which opens a pool at startup for that purpose).
"""

import asyncio
import dataclasses
import logging
import uuid
from typing import Literal

from arq.connections import ArqRedis, RedisSettings
from fastapi import Request

logger = logging.getLogger(__name__)


def redis_settings(url: str | None = None) -> RedisSettings:
    from app.core.config import settings
    rs = RedisSettings.from_dsn(url or settings.REDIS_URL)
    # ARQ's own default conn_timeout is 1 second, which is too tight for
    # Docker Desktop's Windows/WSL2 loopback networking path — the connection
    # succeeds, just not within 1s, so create_pool() fails with a Redis
    # TimeoutError even though `docker exec ... redis-cli ping` and plain
    # redis-py both work fine. 5s costs nothing on a real (Linux) deploy.
    return dataclasses.replace(rs, conn_timeout=5)


async def get_arq_redis(request: Request) -> ArqRedis | None:
    """FastAPI dependency — the pool opened at app startup (see main.py's
    lifespan), for routers that need to enqueue a job. None if Redis was
    unreachable at startup (2026-07-24) — callers must go through
    safe_enqueue below rather than calling .enqueue_job directly."""
    return request.app.state.arq_redis


async def safe_enqueue(
    arq_redis: ArqRedis | None, function: str, *args, **kwargs
) -> Literal["queued", "inline", "dropped"]:
    """Dispatches a background job, preferring the ARQ queue.

    Returns how the job was actually dispatched, so a caller can report the
    truth to the user rather than always claiming "queued":
      · "queued"  — handed to ARQ, a worker will run it
      · "inline"  — no queue available, running in-process right now
      · "dropped" — no queue and no in-process fallback for this job type

    The in-process fallback below runs **only when the enqueue didn't happen**
    (Redis unreachable at startup, or the enqueue itself raised). It used to
    run unconditionally, which was fine for as long as no worker process
    existed — but the moment a real worker consumes the queue, both paths
    call issue_ticket() for the same registration and the student gets two
    ticket emails. That combination never occurred in dev (Docker/Redis
    wasn't reliably up, so a worker was never running alongside the API), so
    it would have fired for the first time in production.

    issue_ticket() is separately idempotent on ticket_sent_at, so this is
    belt-and-braces rather than the only guard.
    """
    if arq_redis is not None:
        try:
            await arq_redis.enqueue_job(function, *args, **kwargs)
            logger.info("Task %r enqueued", function)
            return "queued"
        except Exception as exc:
            logger.warning("ARQ enqueue failed for %r: %s", function, exc)

    # Nothing will consume this job — do the work in-process where we can.
    if function == "send_ticket_email" and args:
        asyncio.create_task(
            _fallback_send_ticket_email(str(args[0]), force=bool(kwargs.get("force", False)))
        )
        return "inline"

    logger.warning(
        "Task %r could not be queued and has no in-process fallback — skipped", function
    )
    return "dropped"


async def _fallback_send_ticket_email(registration_id: str, force: bool = False) -> None:
    from app.db.session import AsyncSessionLocal
    from app.services.sessions.registration import issue_ticket
    try:
        async with AsyncSessionLocal() as db:
            sent = await issue_ticket(db, uuid.UUID(registration_id), force=force)
            await db.commit()
            if sent:
                logger.info("Ticket email sent successfully for registration %s", registration_id)
            else:
                logger.warning("issue_ticket returned False for registration %s (missing contact email or SMTP failure)", registration_id)
    except Exception:
        logger.exception("Ticket email background send failed for registration %s", registration_id)


