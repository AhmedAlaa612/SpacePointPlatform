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
from contextvars import ContextVar, Token

from fastapi import Request

_DEFAULT = "-"

request_id_var: ContextVar[str] = ContextVar("request_id", default=_DEFAULT)
client_ip_var: ContextVar[str] = ContextVar("client_ip", default=_DEFAULT)
user_label_var: ContextVar[str] = ContextVar("user_label", default=_DEFAULT)


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
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    """Single source of truth for logging setup.

    disable_existing_loggers is False on purpose: by the time this runs,
    uvicorn/arq have already created loggers under their own names, and the
    stdlib default of True would silently kill any logger not explicitly
    listed below (e.g. sqlalchemy.engine, httpx) rather than just leaving it
    alone. Explicitly redeclaring uvicorn's logger names is what lets this
    config win over uvicorn's own default dictConfig — see app/main.py.
    """
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"context": {"()": ContextFilter}},
        "formatters": {"json": {"()": JsonFormatter}},
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "filters": ["context"],
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
