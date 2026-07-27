"""The public form's abuse brake.

Rewritten 2026-07-26. It used to trip at 10 requests/minute per IP, which is
wrong in a way that only shows up in the field: a whole venue shares one public
IP, so thirty students registering from a school's WiFi are one bucket, and the
eleventh person gets locked out. These tests pin the new intent — generous
enough that no group of humans notices, strict enough that a script doesn't.

No Redis, no DB, no HTTP client: the limiter is pure in-process logic and
testing it directly is both faster and more precise than driving it through an
endpoint 1001 times.
"""

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core import rate_limit
from app.core.rate_limit import _MAX_REQUESTS, enforce_rate_limit


def _request(*, forwarded: str | None = None, client_host: str = "10.0.0.1") -> Request:
    headers = []
    if forwarded is not None:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    return Request({"type": "http", "headers": headers, "client": (client_host, 12345)})


@pytest.fixture(autouse=True)
def _clean_buckets():
    rate_limit._hits.clear()
    yield
    rate_limit._hits.clear()


def test_a_venue_full_of_people_is_not_throttled():
    """The regression that matters: 200 sign-ups from one shared IP, which is
    what a school workshop looks like from the server's side."""
    for _ in range(200):
        enforce_rate_limit(_request(forwarded="203.0.113.7"))


def test_the_limit_is_generous_enough_for_any_real_group():
    assert _MAX_REQUESTS >= 1000


def test_a_flood_is_still_stopped():
    request = _request(forwarded="203.0.113.8")
    for _ in range(_MAX_REQUESTS):
        enforce_rate_limit(request)

    with pytest.raises(HTTPException) as exc:
        enforce_rate_limit(request)
    assert exc.value.status_code == 429


def test_one_ip_hitting_the_wall_does_not_affect_another():
    hot = _request(forwarded="203.0.113.9")
    for _ in range(_MAX_REQUESTS):
        enforce_rate_limit(hot)
    with pytest.raises(HTTPException):
        enforce_rate_limit(hot)

    enforce_rate_limit(_request(forwarded="203.0.113.10"))  # unaffected


def test_the_bucket_key_is_the_address_nginx_saw_not_the_one_claimed():
    """nginx appends the real peer to X-Forwarded-For, so the rightmost entry
    is ours and everything left of it is caller-supplied. Reading the leftmost
    would let anyone bypass the limit with a spoofed header."""
    enforce_rate_limit(_request(forwarded="1.1.1.1, 203.0.113.11"))
    assert "203.0.113.11" in rate_limit._hits
    assert "1.1.1.1" not in rate_limit._hits


def test_falls_back_to_the_socket_peer_when_unproxied():
    enforce_rate_limit(_request(client_host="192.0.2.5"))
    assert "192.0.2.5" in rate_limit._hits


def test_stale_buckets_are_pruned():
    """Otherwise the dict grows one entry per distinct IP forever — reachable
    the moment nginx starts forwarding real client addresses."""
    enforce_rate_limit(_request(forwarded="203.0.113.12"))
    assert rate_limit._hits

    rate_limit._hits["203.0.113.99"] = [0.0]  # long expired
    rate_limit._last_prune = 0.0
    enforce_rate_limit(_request(forwarded="203.0.113.13"))

    assert "203.0.113.99" not in rate_limit._hits
