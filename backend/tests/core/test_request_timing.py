"""Server-side request timing — see core/timing.py.

The point of these headers is subtraction: a client-observed 20s minus an
`X-Process-Time` of 0.05s says the app was never the problem and the 19.95s
is network, TLS, nginx queueing or a per-IP throttle. That only works if the
header is actually present on ordinary responses, so that is what this pins.
"""

import pytest

from app.core.timing import phase


@pytest.mark.asyncio
async def test_every_response_carries_the_timing_headers(client):
    resp = await client.get("/health")
    assert resp.status_code == 200

    # Parseable as a float — a client subtracting it must never have to
    # special-case a unit suffix.
    assert float(resp.headers["X-Process-Time"]) >= 0

    timing = resp.headers["Server-Timing"]
    assert timing.startswith("total;dur=")
    float(timing.split("total;dur=")[1].split(",")[0])


@pytest.mark.asyncio
async def test_error_responses_are_timed_too(client):
    """The slow requests worth investigating are disproportionately the failing
    ones, so a 4xx must not skip instrumentation."""
    resp = await client.get("/videos/not-a-uuid/playlist", params={"token": "x"})
    assert resp.status_code >= 400
    assert float(resp.headers["X-Process-Time"]) >= 0


@pytest.mark.asyncio
async def test_named_phases_are_reported_and_summed(client, monkeypatch):
    """Phases repeat and nest freely; each name reports one total, so N
    sequential calls in a loop show up as one figure rather than N entries."""
    import app.main as main_module

    @main_module.app.get("/_timing_probe")
    async def _probe():
        for _ in range(3):
            with phase("db"):
                pass
        with phase("r2_download"):
            pass
        return {"ok": True}

    resp = await client.get("/_timing_probe")
    assert resp.status_code == 200
    timing = resp.headers["Server-Timing"]
    assert timing.count("db;dur=") == 1
    assert "r2_download;dur=" in timing


def test_phase_outside_a_request_is_a_no_op():
    """Services call phase() unconditionally; ARQ workers and plain unit tests
    run the same code with no request around it."""
    with phase("db"):
        pass
