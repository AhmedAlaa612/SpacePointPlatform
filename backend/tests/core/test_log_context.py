"""Unit tests for app/core/log_context.py: the IP-extraction relocation
(mirrors the two equivalent cases already covered for the pre-relocation
rate_limit._client_ip), the context filter's bind/default/reset behavior,
and the JSON formatter's output shape.

Same house style as tests/core/test_rate_limit.py: plain sync pytest, a
Request built from a raw ASGI scope dict, autouse fixture resetting module
state around each test — no HTTP client needed for any of this.
"""

import json
import logging
import sys

import pytest
from starlette.requests import Request

from app.core import log_context
from app.core.log_context import (
    ContextFilter,
    JsonFormatter,
    bind_request_context,
    bind_user_label,
    client_ip,
    reset_request_context,
    reset_user_label,
)


def _request(*, forwarded: str | None = None, client_host: str = "10.0.0.1") -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request({"type": "http", "headers": headers, "client": (client_host, 12345)})


def _record(**extra) -> logging.LogRecord:
    record = logging.LogRecord(
        name="app.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


@pytest.fixture(autouse=True)
def _clean_context():
    yield
    log_context.request_id_var.set(log_context._DEFAULT)
    log_context.client_ip_var.set(log_context._DEFAULT)
    log_context.user_label_var.set(log_context._DEFAULT)


def test_client_ip_rightmost_forwarded_entry():
    assert client_ip(_request(forwarded="1.1.1.1, 203.0.113.11")) == "203.0.113.11"


def test_client_ip_falls_back_to_socket_peer():
    assert client_ip(_request(client_host="192.0.2.5")) == "192.0.2.5"


def test_context_filter_injects_defaults_when_nothing_bound():
    record = _record()
    assert ContextFilter().filter(record) is True
    assert record.request_id == "-"
    assert record.client_ip == "-"
    assert record.user_label == "-"


def test_context_filter_injects_bound_values_and_reset_restores_defaults():
    tokens = bind_request_context(request_id="abc123", ip="203.0.113.5")
    user_token = bind_user_label("SP-ST-0075-UAE")
    try:
        record = _record()
        ContextFilter().filter(record)
        assert record.request_id == "abc123"
        assert record.client_ip == "203.0.113.5"
        assert record.user_label == "SP-ST-0075-UAE"
    finally:
        reset_request_context(tokens)
        reset_user_label(user_token)

    after = _record()
    ContextFilter().filter(after)
    assert after.request_id == "-"
    assert after.client_ip == "-"
    assert after.user_label == "-"


def test_json_formatter_produces_valid_json_with_required_keys():
    record = _record(client_ip="203.0.113.5", user_label="SP-ST-0075-UAE", request_id="abc123")
    payload = json.loads(JsonFormatter().format(record))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"
    assert payload["message"] == "hello"
    assert payload["client_ip"] == "203.0.113.5"
    assert payload["user_label"] == "SP-ST-0075-UAE"
    assert payload["request_id"] == "abc123"
    assert "timestamp" in payload


def test_json_formatter_includes_exc_info_on_exception():
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="app.test", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
    payload = json.loads(JsonFormatter().format(record))
    assert "boom" in payload["exc_info"]
