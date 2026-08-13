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


def _sanitize_submission_config(config: dict) -> dict:
    """A submission variant's brief is the one non-quiz config a student is
    *meant* to read — it is the assignment. Rebuilt field by field like the
    quiz sanitiser rather than passed through, so authoring a reviewer-only
    note into the config can never leak it to the student."""
    return {
        "brief": config.get("brief") or "",
        "deliverables": [
            {"title": d.get("title", ""), "detail": d.get("detail", "")}
            for d in (config.get("deliverables") or [])
        ],
        "rubric": [
            {"criterion": r.get("criterion", ""), "detail": r.get("detail", "")}
            for r in (config.get("rubric") or [])
        ],
        "accepted_formats": config.get("accepted_formats") or "",
    }


def variant_student_view(variant: MissionVariant, *, kind: str) -> dict:
    """The JSON-safe payload for a student-facing variant. `quiz` config is
    rebuilt without `is_correct`/`explanation`; `submission` config carries
    the brief and rubric, which the student is meant to read; every other
    kind's config is server-only working data (verifier instructions,
    constraints) with nothing a student should see, so it's omitted.
    """
    raw = variant.config or {}
    if kind == "quiz":
        config = _sanitize_quiz_config(raw)
    elif kind == "submission":
        config = _sanitize_submission_config(raw)
    else:
        config = {}
    return {
        "id": str(variant.id),
        "label": variant.label,
        "position": variant.position,
        "points": variant.points,
        "config": config,
    }
