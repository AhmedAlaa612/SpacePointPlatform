"""Abuse brake for the public registration form (V2 R1-5).

Deliberately generous. This is NOT a fairness quota — it exists only to stop a
script hammering the endpoint, and it must never inconvenience real people.

The original 10-per-minute was far too tight, for a reason that only shows up
in the field: **a whole venue shares one public IP**. Thirty students
registering from a school's WiFi, or a team testing together, all arrive from
the same address. Per-IP limits treat a room as one person, so a sane-looking
cap silently locks everyone out after the first few. 1000/minute is high enough
that no plausible group of humans reaches it, and low enough that a scripted
flood still trips it.

Per-process and in-memory: state isn't shared across backend processes and is
lost on restart. With a threshold this high that's fine — a limit meant to
catch four-digit request rates doesn't need to be exact. Moving it onto Redis
(which now exists in production) is still the answer if this ever needs to be a
real enforcement boundary rather than a brake.
"""

import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

_WINDOW_SECONDS = 60
# Sized to catch attacks, not to ration legitimate use — see module docstring:
# per-IP means per-venue on any shared network, which is the normal case for
# the workshops this form exists to serve.
_MAX_REQUESTS = 1000

_hits: dict[str, list[float]] = defaultdict(list)

# Without this the dict grows one entry per distinct IP forever — a slow leak
# that only becomes reachable once nginx forwards real client addresses.
_PRUNE_EVERY_SECONDS = 300
_last_prune = 0.0


def _client_ip(request: Request) -> str:
    """The address nginx actually saw.

    X-Forwarded-For is a client-supplied header that our proxy *appends* to
    (`$proxy_add_x_forwarded_for`), so the rightmost entry is the peer nginx
    observed and anything to its left is whatever the caller claimed. Reading
    the leftmost value — the usual convention when you trust a chain of proxies
    — would let anyone bypass the limit entirely with a made-up header, since
    there is exactly one proxy here and it is ours.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def _prune(now: float) -> None:
    global _last_prune
    if now - _last_prune < _PRUNE_EVERY_SECONDS:
        return
    _last_prune = now
    stale = [ip for ip, hits in _hits.items() if not hits or now - hits[-1] > _WINDOW_SECONDS]
    for ip in stale:
        del _hits[ip]


def enforce_rate_limit(
    request: Request, *, max_requests: int = _MAX_REQUESTS, window_seconds: int = _WINDOW_SECONDS
) -> None:
    """Raises 429 once this IP exceeds `max_requests` in `window_seconds`.

    Called explicitly inside a route rather than as a FastAPI dependency, so it
    can run after the honeypot check decides whether a request counts at all.
    """
    ip = _client_ip(request)
    now = time.monotonic()
    _prune(now)

    hits = _hits[ip]
    hits[:] = [t for t in hits if now - t < window_seconds]
    if len(hits) >= max_requests:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests — try again shortly")
    hits.append(now)
