"""Mission student-view serializer (P5-4) — the answer-leakage choke point
for mission variants, same posture as `services/lms/serialize.py::student_view`
(§2 of the LMS plan): a quiz variant's `config` holds `is_correct` and
`explanation`, kept out of student hands only by this function and its test.
Rebuilds the allowed shape per kind rather than filtering a blacklist, so an
authoring mistake can't smuggle an answer-shaped key through.
"""

from __future__ import annotations

from app.models.missions.mission import MissionVariant


def _sanitize_quiz_config(config: dict) -> dict:
    return {
        "pass_threshold": config.get("pass_threshold", 0),
        "questions": [
            {
                "prompt": q.get("prompt"),
                "options": [{"text": o.get("text")} for o in (q.get("options") or [])],
            }
            for q in (config.get("questions") or [])
        ],
    }


def variant_student_view(variant: MissionVariant, *, kind: str) -> dict:
    """The JSON-safe payload for a student-facing variant. `quiz` config is
    rebuilt without `is_correct`/`explanation`; every other kind's config is
    server-only working data (verifier instructions, constraints) with
    nothing a student should read directly, so it's omitted entirely.
    """
    config = _sanitize_quiz_config(variant.config or {}) if kind == "quiz" else {}
    return {
        "id": str(variant.id),
        "label": variant.label,
        "position": variant.position,
        "points": variant.points,
        "config": config,
    }
