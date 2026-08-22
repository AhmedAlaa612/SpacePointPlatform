"""services/internship/approval.py::resolve_start_date — boss spec (2026-08-20):
admin override always wins; otherwise auto-resolve against the requested date
and the real approval moment. Pure function, no DB/Redis/HTTP.
"""

from datetime import date, timedelta

from app.services.internship.approval import resolve_start_date


def test_override_always_wins_regardless_of_dates():
    requested = date(2026, 9, 1)
    override = date(2026, 12, 25)
    approval = date(2026, 9, 15)
    assert resolve_start_date(requested, override, approval) == override


def test_approval_on_or_before_requested_uses_requested_date_exactly():
    requested = date(2026, 9, 1)
    assert resolve_start_date(requested, None, requested - timedelta(days=5)) == requested
    assert resolve_start_date(requested, None, requested) == requested


def test_approval_after_requested_uses_the_day_after_approval():
    requested = date(2026, 9, 1)
    approval = requested + timedelta(days=10)
    assert resolve_start_date(requested, None, approval) == approval + timedelta(days=1)


def test_no_request_no_override_falls_back_to_existing_profile_value():
    existing = date(2026, 1, 1)
    assert resolve_start_date(None, None, date(2026, 9, 1), existing) == existing


def test_no_request_no_override_no_existing_is_none():
    assert resolve_start_date(None, None, date(2026, 9, 1)) is None


def test_override_wins_even_with_nothing_requested():
    override = date(2026, 10, 10)
    assert resolve_start_date(None, override, date(2026, 9, 1)) == override
