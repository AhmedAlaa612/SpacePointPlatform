import uuid
from datetime import datetime, timedelta, timezone

import pytest
from app.models.sessions.cohort import Cohort
from app.models.team import Team
from app.services.competitions.timing_windows import (
    get_current_active_window,
    parse_datetime,
    resolve_team_timing,
)


def test_parse_datetime():
    dt = parse_datetime("2026-09-20T18:00:00Z")
    assert dt is not None
    assert dt.tzinfo is not None
    assert dt.hour == 18

    dt2 = parse_datetime("2026-09-20T18:00:00+00:00")
    assert dt2 == dt


def test_resolve_team_timing_no_windows():
    cohort = Cohort(id=uuid.uuid4(), name="Test Cohort", program_id=uuid.uuid4(), submission_windows=[])
    team = Team(id=uuid.uuid4(), name="Test Team", final_locked_at=datetime.now(timezone.utc))

    res = resolve_team_timing(cohort, team)
    assert res["points"] == 0.0
    assert res["is_override"] is False
    assert res["badge"] is None


def test_resolve_team_timing_brackets():
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    t1 = now + timedelta(hours=2)   # 14:00
    t2 = now + timedelta(hours=6)   # 18:00
    t3 = now + timedelta(hours=12)  # 00:00 next day

    windows = [
        {
            "id": "early",
            "name": "Early Bird",
            "cutoff_at": t1.isoformat(),
            "points": 5.0,
            "badge": "Early Bird (+5)",
            "color": "emerald",
        },
        {
            "id": "ontime",
            "name": "On Time",
            "cutoff_at": t2.isoformat(),
            "points": 0.0,
            "badge": "On Time (0)",
            "color": "blue",
        },
        {
            "id": "late",
            "name": "Late",
            "cutoff_at": t3.isoformat(),
            "points": -2.0,
            "badge": "Late (-2)",
            "color": "amber",
        },
    ]

    cohort = Cohort(id=uuid.uuid4(), name="Test Cohort", program_id=uuid.uuid4(), submission_windows=windows)

    # 1. Locked at 13:00 (before Early Bird cutoff 14:00)
    team_early = Team(id=uuid.uuid4(), name="Early Team", final_locked_at=now + timedelta(hours=1))
    res_early = resolve_team_timing(cohort, team_early)
    assert res_early["points"] == 5.0
    assert res_early["tier_name"] == "Early Bird"
    assert res_early["badge"] == "Early Bird (+5)"
    assert res_early["is_override"] is False

    # 2. Locked at 15:00 (after 14:00, before 18:00)
    team_ontime = Team(id=uuid.uuid4(), name="OnTime Team", final_locked_at=now + timedelta(hours=3))
    res_ontime = resolve_team_timing(cohort, team_ontime)
    assert res_ontime["points"] == 0.0
    assert res_ontime["tier_name"] == "On Time"

    # 3. Locked at 20:00 (after 18:00, before 00:00)
    team_late = Team(id=uuid.uuid4(), name="Late Team", final_locked_at=now + timedelta(hours=8))
    res_late = resolve_team_timing(cohort, team_late)
    assert res_late["points"] == -2.0
    assert res_late["tier_name"] == "Late"

    # 4. Locked after all cutoffs (e.g. +15 hours)
    team_critical = Team(id=uuid.uuid4(), name="Crit Team", final_locked_at=now + timedelta(hours=15))
    res_crit = resolve_team_timing(cohort, team_critical)
    assert res_crit["points"] == -2.0  # falls into last window


def test_resolve_team_timing_ops_override():
    windows = [
        {"id": "early", "name": "Early Bird", "cutoff_at": "2026-09-20T18:00:00Z", "points": 5.0},
    ]
    cohort = Cohort(id=uuid.uuid4(), name="Test Cohort", program_id=uuid.uuid4(), submission_windows=windows)

    # Even though locked before cutoff, Ops set a manual override of 3.0 points with notes
    team = Team(
        id=uuid.uuid4(),
        name="Team Override",
        final_locked_at=datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc),
        timing_adjustment_override=3.0,
        timing_adjustment_notes="Approved partial extension",
    )

    res = resolve_team_timing(cohort, team)
    assert res["points"] == 3.0
    assert res["is_override"] is True
    assert res["badge"] == "Override (+3)"
    assert res["override_notes"] == "Approved partial extension"


def test_get_current_active_window():
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    t1 = now + timedelta(hours=2)   # 14:00 (2h remaining)
    t2 = now + timedelta(hours=6)   # 18:00

    windows = [
        {"id": "early", "name": "Early Bird", "cutoff_at": t1.isoformat(), "points": 5.0},
        {"id": "ontime", "name": "On Time", "cutoff_at": t2.isoformat(), "points": 0.0},
    ]

    active = get_current_active_window(windows, now_dt=now)
    assert active is not None
    assert active["id"] == "early"
    assert active["seconds_remaining"] == 7200
    assert active["is_active"] is True
