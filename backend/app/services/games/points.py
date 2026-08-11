"""Live game scoring constants (Live Games Phase 2C, D8) — the single place
`points_mode` becomes an actual number. A question is Normal or Double, not
a facilitator-typed number; `services/games/scoring.py` (8-6) is where the
speed-weighted formula built on top of these numbers lives.
"""

NORMAL_POINTS = 100
DOUBLE_POINTS = 200

POINTS_BY_MODE = {"normal": NORMAL_POINTS, "double": DOUBLE_POINTS}


def max_points_for(points_mode: str) -> int:
    return POINTS_BY_MODE[points_mode]
