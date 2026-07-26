"""Minimal in-memory rate limiter (V2 R1-5).

Per-process, in-memory only — state is not shared across multiple backend
instances/workers, and is lost on restart. This is the explicitly-flagged W1
interim (see MASTER_EXECUTION_PLAN_V2.md R1-5/R2-1): move to a Redis-backed
counter once R2-1 (ARQ + Redis) lands. Fine for a single backend process,
which is all that exists until then.
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 60
_MAX_REQUESTS = 10
_hits: dict[str, list[float]] = defaultdict(list)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(
    request: Request, *, max_requests: int = _MAX_REQUESTS, window_seconds: int = _WINDOW_SECONDS
) -> None:
    """Raises 429 if this IP has made `max_requests` calls in the last
    `window_seconds`. Call this explicitly inside a route (not as a FastAPI
    dependency) so it can run after the honeypot check decides whether this
    request should even count."""
    ip = _client_ip(request)
    now = time.monotonic()
    hits = _hits[ip]
    hits[:] = [t for t in hits if now - t < window_seconds]
    if len(hits) >= max_requests:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests — try again shortly")
    hits.append(now)
