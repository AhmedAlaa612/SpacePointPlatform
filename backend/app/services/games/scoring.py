"""Live games — scoring (Live Games Phase 2C, 8-6, D8).

Correctness required, speed-weighted: a wrong (or missing/timed-out)
answer always scores 0, regardless of speed. A correct answer decays
*linearly* from the question's `max_points` (100 or 200, `services
.games.points.max_points_for`) down to a floor share as more of the
time limit gets used — `floor_pct` is configurable per session
assignment (`GameSessionAssignment.floor_pct`, default 25).

    points = floor_pts + (max_pts - floor_pts) * (1 - elapsed / time_limit)
    floor_pts = max_pts * floor_pct / 100

A correct answer at the buzzer still earns `floor_pts`, never zero —
that's the whole point of a floor. Rounded to the nearest whole point
since every amount `award_points` writes is an integer.
"""


def score_answer(
    *, is_correct: bool, max_points: int, floor_pct: int, elapsed_seconds: float, time_limit_seconds: int,
) -> int:
    if not is_correct:
        return 0
    elapsed = max(0.0, min(elapsed_seconds, time_limit_seconds))
    floor_points = max_points * floor_pct / 100
    points = floor_points + (max_points - floor_points) * (1 - elapsed / time_limit_seconds)
    return round(points)
