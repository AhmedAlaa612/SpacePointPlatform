"""Server-side request timing — the one number the competition-day load
investigation never had.

Every latency figure in that investigation was client-observed wall clock:
DNS + TCP + TLS + nginx accept/queue + upstream time, collapsed into one
number with no way to tell which part moved. Two rounds of backend
optimisation (#51, #52) went in against numbers that could not have shown
whether the backend was even involved.

This measures the only span the application can actually see — from the
moment uvicorn hands us the request to the moment we hand back the response
start — and, within it, named phases the routes declare themselves.

Two outputs, both cheap enough to leave on in production:

- `X-Process-Time: 0.0143` — total in-app seconds. Subtract it from a
  client-observed time and the remainder is everything *outside* the app
  (network, TLS, nginx queueing, per-IP throttling). That subtraction is
  the whole point.
- `Server-Timing: total;dur=14.3, r2;dur=11.9, db;dur=1.4` — milliseconds
  per phase, in the standard header browsers show natively in devtools'
  network panel.

`phase()` is a plain (non-async) context manager on purpose: it only reads
the clock on enter and exit, so wrapping an `await` in it works and measures
the await's full duration, including any time the coroutine spent parked
waiting for a thread-pool token or a DB connection. That parked time is
exactly what we are hunting, so it must be inside the measurement, not
excluded from it.
"""

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger(__name__)

# Per-request accumulator: phase name -> total seconds spent in it. A
# ContextVar rather than request state so `phase()` is callable from any
# service-layer function without threading a Request object down to it.
# Phases nest and repeat freely; time is summed per name, so N sequential
# presign calls report as one `presign` total.
_phases: ContextVar[dict[str, float] | None] = ContextVar("request_phases", default=None)


@contextmanager
def phase(name: str):
    """Attribute the wrapped block's wall time to `name` on this request.

    A no-op outside a request (background jobs, tests, the ARQ workers), so
    services can use it unconditionally.
    """
    bucket = _phases.get()
    if bucket is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        bucket[name] = bucket.get(name, 0.0) + (time.perf_counter() - started)


def _server_timing(total: float, phases: dict[str, float]) -> str:
    parts = [f"total;dur={total * 1000:.1f}"]
    parts += [f"{name};dur={secs * 1000:.1f}" for name, secs in sorted(phases.items())]
    return ", ".join(parts)


class TimingMiddleware:
    """Raw ASGI middleware, deliberately not Starlette's BaseHTTPMiddleware.

    BaseHTTPMiddleware wraps every request in an anyio task group and pipes
    the response body through a memory stream. That is real per-request
    overhead on the exact event loop whose saturation is under investigation
    — a measuring instrument that changes what it measures. This adds one
    `perf_counter()` pair, one dict, and a header write.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        phases: dict[str, float] = {}
        token = _phases.set(phases)
        started = time.perf_counter()
        status_code = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                elapsed = time.perf_counter() - started
                headers = MutableHeaders(scope=message)
                headers["X-Process-Time"] = f"{elapsed:.4f}"
                headers["Server-Timing"] = _server_timing(elapsed, phases)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _phases.reset(token)
            elapsed = time.perf_counter() - started
            threshold = settings.SLOW_REQUEST_SECONDS
            if threshold and elapsed >= threshold:
                # Logged rather than only returned as a header because the
                # interesting requests during a burst are the ones whose
                # client gave up before reading any header at all.
                logger.warning(
                    "slow request %.3fs %s %s -> %s [%s]",
                    elapsed,
                    scope.get("method", "?"),
                    scope.get("path", "?"),
                    status_code or "no-response",
                    _server_timing(elapsed, phases),
                )
