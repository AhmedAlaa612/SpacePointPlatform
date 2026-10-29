"""Submission timing windows & brackets evaluation service.
Handles dynamic bracket resolution (Early Bird, On-Time, Late penalties)
for both Checkpoints and Final Submissions, as well as Ops manual overrides.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.models.sessions.cohort import Cohort
from app.models.team import Team


def parse_datetime(val: Any) -> datetime | None:
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, str):
        try:
            cleaned = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def filter_windows_for_gate(windows_raw: Any, checkpoint_id: str | uuid.UUID | None = None) -> list[dict]:
    """Filters cohort submission windows for a specific gate.
    If `checkpoint_id` is None, returns windows for the Final Submission Gate (where checkpoint_id is None, empty, or 'final').
    If `checkpoint_id` is provided, returns windows matching that checkpoint ID.
    """
    if isinstance(windows_raw, str):
        try:
            windows_raw = json.loads(windows_raw)
        except Exception:
            windows_raw = []
    if not isinstance(windows_raw, list):
        windows_raw = []

    valid = [w for w in windows_raw if isinstance(w, dict)]
    if checkpoint_id is None:
        return [w for w in valid if not w.get("checkpoint_id") or w.get("checkpoint_id") == "final"]

    cid_str = str(checkpoint_id)
    return [w for w in valid if str(w.get("checkpoint_id") or "") == cid_str]


def resolve_single_gate_timing(windows: list[dict], locked_at_val: Any) -> dict[str, Any]:
    """Resolves timing points for a single gate (Final Submission or a Checkpoint)
    against its configured windows based on its locked_at timestamp.
    """
    locked_at = parse_datetime(locked_at_val)
    if not windows or not locked_at:
        return {
            "points": 0.0,
            "badge": None,
            "tier_name": None,
            "color": None,
            "locked_at": locked_at,
        }

    # Sort windows by cutoff_at ascending
    sorted_windows = sorted(
        windows,
        key=lambda w: parse_datetime(w.get("cutoff_at")) or datetime.max.replace(tzinfo=timezone.utc),
    )

    for w in sorted_windows:
        cutoff = parse_datetime(w.get("cutoff_at"))
        if cutoff and locked_at <= cutoff:
            pts_raw = w.get("points")
            try:
                pts = float(pts_raw) if pts_raw is not None else 0.0
            except (ValueError, TypeError):
                pts = 0.0
            return {
                "points": pts,
                "badge": w.get("badge") or f"{w.get('name', 'Tier')} ({'+' if pts > 0 else ''}{pts:g})",
                "tier_name": w.get("name"),
                "color": w.get("color") or ("green" if pts > 0 else ("rose" if pts < 0 else "white")),
                "locked_at": locked_at,
            }

    # Passed all cutoffs -> if last window was a penalty (pts < 0), apply it; otherwise 0.0
    if sorted_windows and not sorted_windows[-1].get("is_deadline"):
        last = sorted_windows[-1]
        pts_raw = last.get("points")
        try:
            pts = float(pts_raw) if pts_raw is not None else 0.0
        except (ValueError, TypeError):
            pts = 0.0
        if pts < 0:
            return {
                "points": pts,
                "badge": last.get("badge") or f"{last.get('name', 'Late')} ({pts:g})",
                "tier_name": last.get("name"),
                "color": last.get("color") or "rose",
                "locked_at": locked_at,
            }

    return {
        "points": 0.0,
        "badge": None,
        "tier_name": None,
        "color": None,
        "locked_at": locked_at,
    }


def resolve_team_timing(
    cohort: Cohort | None,
    team: Team | None,
    checkpoint_states: list[dict] | None = None,
) -> dict[str, Any]:
    """Resolves timing adjustments for a team.
    Combines checkpoint submission timing and final lock timing.
    Priority:
    1. If team has `timing_adjustment_override` set by Ops, that value overrides the net points.
    2. Otherwise, net points = final lock points + sum of all checkpoint timing points.
    Includes itemized `breakdown` of every gate.
    """
    if team is None:
        return {
            "points": 0.0,
            "badge": None,
            "tier_name": None,
            "color": None,
            "is_override": False,
            "override_notes": None,
            "locked_at": None,
            "first_locked_at": None,
            "calculated_total": 0.0,
            "breakdown": [],
        }

    windows_raw = getattr(cohort, "submission_windows", None) if cohort else None
    final_locked_at = getattr(team, "final_locked_at", None)

    # 1. Evaluate Checkpoint Gates (if provided)
    breakdown: list[dict[str, Any]] = []
    checkpoint_total = 0.0
    if checkpoint_states:
        for cs in checkpoint_states:
            cp_id = cs.get("item_id")
            cp_title = cs.get("title") or "Checkpoint"
            cp_locked_at = cs.get("locked_at")
            cp_windows = filter_windows_for_gate(windows_raw, cp_id)
            cp_res = resolve_single_gate_timing(cp_windows, cp_locked_at)
            checkpoint_total += cp_res["points"]
            breakdown.append({
                "gate_id": str(cp_id),
                "title": cp_title,
                "type": "checkpoint",
                "points": cp_res["points"],
                "badge": cp_res["badge"],
                "tier_name": cp_res["tier_name"],
                "color": cp_res["color"],
                "locked_at": cp_res["locked_at"],
            })

    # 2. Evaluate Final Gate
    final_windows = filter_windows_for_gate(windows_raw, None)
    final_res = resolve_single_gate_timing(final_windows, final_locked_at)
    breakdown.append({
        "gate_id": "final",
        "title": "Final Submission",
        "type": "final",
        "points": final_res["points"],
        "badge": final_res["badge"],
        "tier_name": final_res["tier_name"],
        "color": final_res["color"],
        "locked_at": final_res["locked_at"],
    })

    calculated_total = round(final_res["points"] + checkpoint_total, 1)

    # 3. Check Manual Ops Override
    override_val = getattr(team, "timing_adjustment_override", None)
    if override_val is not None:
        try:
            pts = float(override_val)
        except (ValueError, TypeError):
            pts = 0.0
        sign = "+" if pts > 0 else ""
        return {
            "points": pts,
            "badge": f"Override ({sign}{pts:g})",
            "tier_name": "Manual Override",
            "color": "purple",
            "is_override": True,
            "override_notes": getattr(team, "timing_adjustment_notes", None),
            "locked_at": final_locked_at,
            "first_locked_at": getattr(team, "first_locked_at", None),
            "calculated_total": calculated_total,
            "breakdown": breakdown,
        }

    # If only Final Gate was configured and no checkpoints, preserve previous exact badge formatting
    if not checkpoint_states and final_res["badge"]:
        badge = final_res["badge"]
        tier_name = final_res["tier_name"]
        color = final_res["color"]
    elif calculated_total != 0.0:
        sign = "+" if calculated_total > 0 else ""
        badge = f"{sign}{calculated_total:g} pts"
        tier_name = "Timing Adjustment"
        color = "green" if calculated_total > 0 else "rose"
    else:
        badge = None
        tier_name = None
        color = None

    return {
        "points": calculated_total,
        "badge": badge,
        "tier_name": tier_name,
        "color": color,
        "is_override": False,
        "override_notes": None,
        "locked_at": final_locked_at,
        "first_locked_at": getattr(team, "first_locked_at", None),
        "calculated_total": calculated_total,
        "breakdown": breakdown,
    }


def is_cohort_deadline_passed(
    windows: Any,
    now_dt: datetime | None = None,
    checkpoint_id: str | uuid.UUID | None = None,
) -> bool:
    """Returns True if any window marked with `is_deadline=True` for the target gate
    (Final Submission if checkpoint_id is None, or specific checkpoint) has a cutoff in the past.
    """
    gate_windows = filter_windows_for_gate(windows, checkpoint_id)
    if not gate_windows:
        return False

    now = now_dt or datetime.now(timezone.utc)
    if not now.tzinfo:
        now = now.replace(tzinfo=timezone.utc)

    for w in gate_windows:
        if isinstance(w, dict) and w.get("is_deadline"):
            cutoff = parse_datetime(w.get("cutoff_at"))
            if cutoff and now > cutoff:
                return True
    return False


def is_checkpoint_deadline_passed(
    windows: Any,
    checkpoint_id: str | uuid.UUID,
    now_dt: datetime | None = None,
) -> bool:
    """Shortcut to check if a specific checkpoint's deadline has passed."""
    return is_cohort_deadline_passed(windows, now_dt=now_dt, checkpoint_id=checkpoint_id)


def get_current_active_window(
    windows: Any,
    now_dt: datetime | None = None,
    checkpoint_id: str | uuid.UUID | None = None,
) -> dict[str, Any] | None:
    """Finds the submission window currently active for a gate.
    Returns window details and `seconds_remaining` until this window's cutoff.
    If all windows have expired, returns None.
    """
    gate_windows = filter_windows_for_gate(windows, checkpoint_id)
    if not gate_windows:
        return None

    now = now_dt or datetime.now(timezone.utc)
    if not now.tzinfo:
        now = now.replace(tzinfo=timezone.utc)

    sorted_windows = sorted(
        gate_windows,
        key=lambda w: parse_datetime(w.get("cutoff_at")) or datetime.max.replace(tzinfo=timezone.utc),
    )

    for w in sorted_windows:
        cutoff = parse_datetime(w.get("cutoff_at"))
        if cutoff and now <= cutoff:
            secs = max(0, int((cutoff - now).total_seconds()))
            return {
                **w,
                "seconds_remaining": secs,
                "is_active": True,
            }

    return None


def get_current_active_checkpoint_window(
    windows: Any,
    checkpoint_id: str | uuid.UUID,
    now_dt: datetime | None = None,
) -> dict[str, Any] | None:
    """Shortcut to get the active window for a specific checkpoint."""
    return get_current_active_window(windows, now_dt=now_dt, checkpoint_id=checkpoint_id)
