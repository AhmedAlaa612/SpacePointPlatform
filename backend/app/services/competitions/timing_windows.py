"""Submission timing windows & brackets evaluation service.
Handles dynamic bracket resolution (Early Bird, On-Time, Late penalties)
as well as Ops manual overrides for competition teams.
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
            # Handle ISO string with or without Z
            cleaned = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(cleaned)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def resolve_team_timing(cohort: Cohort | None, team: Team | None) -> dict[str, Any]:
    """Resolves the timing adjustment for a team.
    Priority:
    1. If team has `timing_adjustment_override` set by Ops, use that value directly.
    2. Otherwise, resolve team's `final_locked_at` against `cohort.submission_windows`.
    3. If no windows configured or team not locked, default to 0.0 points.
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
        }

    # 1. Manual Ops Override
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
            "locked_at": getattr(team, "final_locked_at", None),
            "first_locked_at": getattr(team, "first_locked_at", None),
        }

    locked_at = parse_datetime(getattr(team, "final_locked_at", None))
    windows_raw = getattr(cohort, "submission_windows", None) if cohort else None
    if isinstance(windows_raw, str):
        try:
            windows_raw = json.loads(windows_raw)
        except Exception:
            windows_raw = []
    if not isinstance(windows_raw, list):
        windows_raw = []

    valid_windows = [w for w in windows_raw if isinstance(w, dict)]

    if not valid_windows or not locked_at:
        return {
            "points": 0.0,
            "badge": None,
            "tier_name": None,
            "color": None,
            "is_override": False,
            "override_notes": None,
            "locked_at": getattr(team, "final_locked_at", None),
            "first_locked_at": getattr(team, "first_locked_at", None),
        }

    # Sort windows by cutoff_at ascending
    windows = sorted(
        valid_windows,
        key=lambda w: parse_datetime(w.get("cutoff_at")) or datetime.max.replace(tzinfo=timezone.utc),
    )

    for w in windows:
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
                "color": w.get("color") or ("emerald" if pts > 0 else ("rose" if pts < 0 else "blue")),
                "is_override": False,
                "override_notes": None,
                "locked_at": getattr(team, "final_locked_at", None),
                "first_locked_at": getattr(team, "first_locked_at", None),
            }

    # Passed all cutoffs -> take the last window (critical late / lockout)
    if windows:
        last = windows[-1]
        pts_raw = last.get("points")
        try:
            pts = float(pts_raw) if pts_raw is not None else 0.0
        except (ValueError, TypeError):
            pts = 0.0
        return {
            "points": pts,
            "badge": last.get("badge") or f"{last.get('name', 'Late')} ({'+' if pts > 0 else ''}{pts:g})",
            "tier_name": last.get("name"),
            "color": last.get("color") or "rose",
            "is_override": False,
            "override_notes": None,
            "locked_at": getattr(team, "final_locked_at", None),
            "first_locked_at": getattr(team, "first_locked_at", None),
        }

    return {
        "points": 0.0,
        "badge": None,
        "tier_name": None,
        "color": None,
        "is_override": False,
        "override_notes": None,
        "locked_at": getattr(team, "final_locked_at", None),
        "first_locked_at": getattr(team, "first_locked_at", None),
    }


def get_current_active_window(windows: Any, now_dt: datetime | None = None) -> dict[str, Any] | None:
    """Finds the submission window currently active for a team locking right now.
    Returns window details and `seconds_remaining` until this window's cutoff.
    """
    if isinstance(windows, str):
        try:
            windows = json.loads(windows)
        except Exception:
            windows = []
    if not isinstance(windows, list):
        return None

    valid_windows = [w for w in windows if isinstance(w, dict)]
    if not valid_windows:
        return None

    now = now_dt or datetime.now(timezone.utc)
    if not now.tzinfo:
        now = now.replace(tzinfo=timezone.utc)

    sorted_windows = sorted(
        valid_windows,
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

    # All cutoffs expired
    if sorted_windows:
        last = sorted_windows[-1]
        return {
            **last,
            "seconds_remaining": 0,
            "is_active": False,
            "is_past_all_cutoffs": True,
        }
    return None
