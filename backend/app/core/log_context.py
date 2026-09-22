"""Structured JSON logging.

Per-request context (contextvars), the filter that injects it into every
LogRecord, the JSON formatter, and the single configure_logging() entrypoint
both the API process (app/main.py) and the worker process (app/workers/main.py)
call.

Two logging processes, two different call sites — see the comment at each
call site for why: uvicorn (app/main.py) runs its own dictConfig before
importing the ASGI app, so configure_logging() at import time wins. arq
(app/workers/main.py) runs its own dictConfig *after* importing the worker
settings module, so a bare import-time call there would be silently
overwritten — that one has to hook WorkerSettings.on_startup instead.
"""

import json
import logging
import logging.config
import time
import uuid
from contextvars import ContextVar, Token

from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_DEFAULT = "-"

request_id_var: ContextVar[str] = ContextVar("request_id", default=_DEFAULT)
client_ip_var: ContextVar[str] = ContextVar("client_ip", default=_DEFAULT)
user_label_var: ContextVar[str] = ContextVar("user_label", default=_DEFAULT)
start_time_var: ContextVar[float | None] = ContextVar("start_time", default=None)


def client_ip(request: Request) -> str:
    """The address nginx actually saw.

    Relocated from rate_limit.py::_client_ip — X-Forwarded-For is a
    client-supplied header that our proxy *appends* to
    (`$proxy_add_x_forwarded_for`), so the rightmost entry is the peer nginx
    observed and anything to its left is whatever the caller claimed. Reading
    the leftmost value — the usual convention when you trust a chain of
    proxies — would let anyone spoof it, since there is exactly one proxy
    here and it is ours. Single source of truth now that both the rate
    limiter and request logging need it.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [p.strip() for p in forwarded.split(",") if p.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def bind_request_context(*, request_id: str, ip: str) -> tuple[Token, Token]:
    """Called by the request-logging middleware at the start of every HTTP
    request. Returns the tokens reset_request_context needs."""
    return request_id_var.set(request_id), client_ip_var.set(ip)


def reset_request_context(tokens: tuple[Token, Token]) -> None:
    request_id_token, client_ip_token = tokens
    request_id_var.reset(request_id_token)
    client_ip_var.reset(client_ip_token)


def bind_user_label(label: str) -> Token:
    """Called by get_current_user / get_current_user_optional once `user`
    is resolved, and once (with the default) by the middleware before that,
    so there's always a token to reset even on an unauthenticated request."""
    return user_label_var.set(label)


def reset_user_label(token: Token) -> None:
    user_label_var.reset(token)


class RequestContextMiddleware:
    """Raw ASGI middleware — deliberately not `@app.middleware("http")`
    (BaseHTTPMiddleware).

    The previous version used BaseHTTPMiddleware and reset context in a
    `finally` right after `call_next()` returned. That's provably too
    early: BaseHTTPMiddleware's dispatch function only *builds* the
    response — Starlette sends it (calls the real ASGI `send`) afterward,
    outside that function's stack frame. uvicorn's access-log line fires
    synchronously inside that `send` call (h11_impl.py/httptools_impl.py),
    and an unhandled exception's traceback is logged through `uvicorn.error`
    even further out. Both were confirmed empirically (a temporary log
    line inside an endpoint showed the correct request_id/client_ip; the
    uvicorn.access line for that same request, right after, showed "-"/"-"
    every time) to be seeing the post-reset defaults instead of the
    request's real values — the two log lines you'd most want to
    correlate were exactly the two that couldn't be.

    A raw ASGI middleware's `self.app(scope, receive, send)` call instead
    covers the *entire* request — routing, the response, every `send()`
    call including the one that fires the access log, and any exception
    logged while unwinding back out through this layer — inside one
    uninterrupted await, in this same task. The `finally` below therefore
    runs strictly after all of that.

    Resetting at all — rather than relying solely on uvicorn's own
    per-request task isolation (it hands each HTTP request task a fresh,
    empty `contextvars.Context()`, so nothing set here could leak into a
    different *uvicorn* request even without an explicit reset) — is still
    necessary: `httpx`'s `ASGITransport` (what the test suite's `client`
    fixture uses) calls `self.app(scope, receive, send)` directly with no
    per-request task boundary, so sequential requests within one test
    would otherwise share whatever context the previous one left bound.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:12]
        tokens = bind_request_context(request_id=request_id, ip=client_ip(Request(scope)))
        user_token = bind_user_label("-")
        start_time_token = start_time_var.set(time.perf_counter())

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            reset_request_context(tokens)
            reset_user_label(user_token)
            start_time_var.reset(start_time_token)


class ContextFilter(logging.Filter):
    """Stamps every LogRecord with the current contextvars.

    Runs for worker-process records too — those vars just stay at their "-"
    default there, since a background job has no HTTP request to bind from.
    That's an accepted gap for this pass, not a bug.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.client_ip = client_ip_var.get()
        record.user_label = user_label_var.get()
        start = start_time_var.get()
        if start is not None and record.name == "uvicorn.access":
            record.duration_ms = round((time.perf_counter() - start) * 1000, 2)
        return True


class NoiseFilter(logging.Filter):
    """Drops high-frequency 200/304 polling and health-check lines from uvicorn.access.

    Failed requests (4xx / 5xx) on these endpoints are never suppressed.
    """

    SILENCED_PATHS = ("/notifications/me", "/health", "/health/worker")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) >= 5:
            path = str(record.args[2])
            status = record.args[4]
            if any(path == p or path.startswith(f"{p}?") for p in self.SILENCED_PATHS):
                if status in (200, 304, "200", "304"):
                    return False
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line — timestamp, level, logger, message, plus
    the request context ContextFilter attached."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "client_ip": getattr(record, "client_ip", _DEFAULT),
            "user_label": getattr(record, "user_label", _DEFAULT),
            "request_id": getattr(record, "request_id", _DEFAULT),
        }

        # Extract structured HTTP telemetry fields for Axiom/dashboards
        method = getattr(record, "method", None)
        path = getattr(record, "path", None)
        status_code = getattr(record, "status_code", None)

        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) >= 5:
            method = method or record.args[1]
            path = path or record.args[2]
            status_code = status_code if status_code is not None else record.args[4]

        if method is not None:
            payload["method"] = str(method)
        if path is not None:
            payload["path"] = str(path)
        if status_code is not None:
            try:
                payload["status_code"] = int(status_code)
            except (ValueError, TypeError):
                payload["status_code"] = status_code

        if hasattr(record, "duration_ms") and record.duration_ms is not None:
            payload["duration_ms"] = record.duration_ms

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_VALID_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}


def configure_logging(level: str = "INFO") -> None:
    """Single source of truth for logging setup.

    disable_existing_loggers is False on purpose: by the time this runs,
    uvicorn/arq have already created loggers under their own names, and the
    stdlib default of True would silently kill any logger not explicitly
    listed below (e.g. sqlalchemy.engine, httpx) rather than just leaving it
    alone. Explicitly redeclaring uvicorn's logger names is what lets this
    config win over uvicorn's own default dictConfig — see app/main.py.

    `level` comes straight from the LOG_LEVEL env var (settings.py has no
    validator on it — it's a bare str) — dictConfig's own level lookup is
    case-sensitive and raises ValueError on anything it doesn't recognize
    (confirmed: 'info' crashes it, not just typos like 'DEGUB'). That
    ValueError happens at import time in app/main.py, before the app
    object even exists, so both the API and both arq workers would
    crash-loop on nothing worse than a lowercase .env value. Normalizing
    here, with a silent fallback to INFO on anything still unrecognized
    after that, means a bad LOG_LEVEL degrades logging verbosity, not the
    whole service.
    """
    level = level.upper()
    if level not in _VALID_LEVELS:
        level = "INFO"
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": ContextFilter},
            "noise": {"()": NoiseFilter},
        },
        "formatters": {"json": {"()": JsonFormatter}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "filters": ["context", "noise"],
                "stream": "ext://sys.stdout",
            }
        },
        "root": {"handlers": ["console"], "level": level},
        "loggers": {
            "uvicorn": {"handlers": ["console"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["console"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["console"], "level": level, "propagate": False},
            "arq": {"handlers": ["console"], "level": level, "propagate": False},
            "arq.worker": {"handlers": ["console"], "level": level, "propagate": False},
        },
    }
    logging.config.dictConfig(config)
