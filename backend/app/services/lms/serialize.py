"""LMS student-view serializer (LM1-2) — the answer-leakage choke point (§2).

JSONB content has no DB-level guard: `is_correct` and `explanation` sitting
inside `module_items.content` are only kept out of students' hands by exactly
this function and its test (§DISCOVERIES 8). Every kind is rebuilt, not
filtered — whitelisting the keys a kind is allowed to have is stronger than
blacklisting two keys, because a stray authoring mistake can't smuggle an
answer-shaped key through a copy that happens to preserve everything else.

`pass_threshold` is NOT an answer and stays — the player needs it to show the
pass mark. Flashcards keep term + definition: the mode of play is
click-to-reveal, so the card text is the content, not a secret.

Video checkpoints (2026-08-07) go through `sanitize_checkpoint` below, not
this module's `student_view` — they're not `ModuleItem` rows, they're child
rows of a video item, fetched and sanitized separately by the student router.
"""

from __future__ import annotations

import uuid

from app.models.lms.course import ModuleItem, VideoCheckpoint


def _sanitize_quiz(content: dict) -> dict:
    return {
        "pass_threshold": content.get("pass_threshold", 0),
        "questions": [
            {
                "prompt": q.get("prompt"),
                "options": [{"text": o.get("text")} for o in (q.get("options") or [])],
            }
            for q in (content.get("questions") or [])
        ],
    }


def _sanitize_text(content: dict) -> dict:
    return {"body": content.get("body")}


def _sanitize_flashcards(content: dict) -> dict:
    return {
        "title": content.get("title"),
        "cards": [
            {"term": c.get("term"), "definition": c.get("definition")}
            for c in (content.get("cards") or [])
        ],
    }


def _sanitize_attachment(content: dict) -> dict:
    # bucket/path are internal storage details, not the student's business —
    # same posture as video's token-gated stream: the actual viewing URL
    # comes from a dedicated endpoint (GET .../attachment/url), not this
    # payload, so nothing here needs signing or expiry handling.
    return {"filename": content.get("filename"), "size_bytes": content.get("size_bytes")}


def _sanitize_mission(content: dict) -> dict:
    # Nothing secret here — mission_id/variant_id are pointers, not answers.
    # The router enriches with mission_title/points/attempt_status (P5-5),
    # same two-step shape ContentVideo's transcode_status already uses.
    return {"mission_id": content.get("mission_id"), "variant_id": content.get("variant_id")}


def _sanitize(kind: str, content: dict | None) -> dict:
    content = content or {}
    if kind == "quiz":
        return _sanitize_quiz(content)
    if kind == "text":
        return _sanitize_text(content)
    if kind == "flashcards":
        return _sanitize_flashcards(content)
    if kind == "attachment":
        return _sanitize_attachment(content)
    if kind == "mission":
        return _sanitize_mission(content)
    # video (and any unknown kind) exposes nothing from the JSONB at all —
    # it carries `{}` by design and everything real lives in module_videos.
    return {}


def student_view(item: ModuleItem) -> dict:
    """The JSON-safe, answer-free payload for a student-facing item.

    This is what LM1-3's module read calls for every item. Guarantees: the
    returned dict (at any depth) contains no `is_correct` and no
    `explanation` key, for every kind — pinned by test_lms_services.py's leak
    test. Pydantic response models on the routes enforce it a second time.
    """
    return {
        "id": str(item.id),
        "kind": item.kind,
        "title": item.title,
        "position": item.position,
        "content": _sanitize(item.kind, item.content),
    }


def sanitize_checkpoint(checkpoint: VideoCheckpoint) -> dict:
    """The JSON-safe payload for a student-facing checkpoint — no `correct`,
    no `explanation` (that's post-answer only, same posture as quiz review)."""
    content = checkpoint.content or {}
    if checkpoint.kind == "note":
        sanitized = {"body": content.get("body")}
    else:
        options = content.get("options")
        sanitized = {
            "question_type": content.get("question_type"),
            "prompt": content.get("prompt"),
            "options": [{"text": o.get("text")} for o in options] if options else None,
        }
    return {
        "id": str(checkpoint.id),
        "start_seconds": checkpoint.start_seconds,
        "end_seconds": checkpoint.end_seconds,
        "kind": checkpoint.kind,
        "content": sanitized,
    }