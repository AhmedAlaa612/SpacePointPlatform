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


def test_checkpoint_timing_windows_and_aggregation():
    cp1_id = str(uuid.uuid4())
    cp2_id = str(uuid.uuid4())

    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    t1 = now + timedelta(hours=2)   # 14:00 Checkpoint 1 Early
    t2 = now + timedelta(hours=4)   # 16:00 Checkpoint 1 Deadline
    t3 = now + timedelta(hours=6)   # 18:00 Final Lock Early
    t4 = now + timedelta(hours=8)   # 20:00 Final Lock On-time

    windows = [
        # Checkpoint 1 windows
        {"id": "cp1-early", "name": "CP1 Early", "cutoff_at": t1.isoformat(), "points": 3.0, "checkpoint_id": cp1_id},
        {"id": "cp1-deadline", "name": "CP1 Deadline", "cutoff_at": t2.isoformat(), "points": 0.0, "checkpoint_id": cp1_id, "is_deadline": True},
        # Final lock windows
        {"id": "final-early", "name": "Final Early", "cutoff_at": t3.isoformat(), "points": 5.0, "checkpoint_id": None},
        {"id": "final-ontime", "name": "Final On-Time", "cutoff_at": t4.isoformat(), "points": 0.0, "checkpoint_id": None},
    ]

    cohort = Cohort(id=uuid.uuid4(), name="Test Cohort", program_id=uuid.uuid4(), submission_windows=windows)

    # 1. Team locked CP1 early (13:00 -> +3 pts), Final locked on-time (19:00 -> 0 pts)
    team = Team(id=uuid.uuid4(), name="Alpha Team", final_locked_at=now + timedelta(hours=7))
    checkpoint_states = [
        {"item_id": cp1_id, "title": "Checkpoint 1", "locked_at": now + timedelta(hours=1), "status": "done"},
        {"item_id": cp2_id, "title": "Checkpoint 2", "locked_at": None, "status": "pending"},
    ]

    res = resolve_team_timing(cohort, team, checkpoint_states=checkpoint_states)
    assert res["points"] == 3.0  # 3.0 from CP1 + 0.0 from Final
    assert res["calculated_total"] == 3.0
    assert len(res["breakdown"]) == 3  # CP1, CP2, Final
    assert res["breakdown"][0]["points"] == 3.0
    assert res["breakdown"][1]["points"] == 0.0
    assert res["breakdown"][2]["points"] == 0.0


def test_is_checkpoint_deadline_passed():
    from app.services.competitions.timing_windows import is_checkpoint_deadline_passed, is_cohort_deadline_passed

    cp_id = str(uuid.uuid4())
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    t_past = now - timedelta(hours=1)
    t_future = now + timedelta(hours=1)

    windows = [
        {"id": "cp-dead", "name": "CP Deadline", "cutoff_at": t_past.isoformat(), "checkpoint_id": cp_id, "is_deadline": True},
        {"id": "final-dead", "name": "Final Deadline", "cutoff_at": t_future.isoformat(), "checkpoint_id": None, "is_deadline": True},
    ]

    # Checkpoint deadline has passed
    assert is_checkpoint_deadline_passed(windows, cp_id, now_dt=now) is True
    # Final deadline has NOT passed
    assert is_cohort_deadline_passed(windows, now_dt=now, checkpoint_id=None) is False


def test_cloned_windows_checkpoint_remapping():
    old_cp1 = str(uuid.uuid4())
    new_cp1 = str(uuid.uuid4())
    item_id_map = {old_cp1: new_cp1}

    source_windows = [
        {"id": "tier-1", "name": "Early", "checkpoint_id": old_cp1, "points": 5.0},
        {"id": "tier-2", "name": "Final Lock", "checkpoint_id": None, "points": 10.0},
    ]

    remapped = []
    for w in source_windows:
        if isinstance(w, dict) and w.get("checkpoint_id") and str(w["checkpoint_id"]) in item_id_map:
            remapped.append({**w, "checkpoint_id": item_id_map[str(w["checkpoint_id"])]})
        else:
            remapped.append(w)

    assert remapped[0]["checkpoint_id"] == new_cp1
    assert remapped[1]["checkpoint_id"] is None


