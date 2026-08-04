"""LMS student-view serializer (LM1-2) — the answer-leakage choke point (§2).

JSONB content has no DB-level guard: `is_correct` and `explanation` sitting
inside `module_items.content` are only kept out of students' hands by exactly
this function and its test (§DISCOVERIES 8). Every kind is rebuilt, not
filtered — whitelisting the keys a kind is allowed to have is stronger than
blacklisting two keys, because a stray authoring mistake can't smuggle an
answer-shaped key through a copy that happens to preserve everything else.

`mid_video_at_seconds` and `pass_threshold` are NOT answers and stay — the
player needs both to time the checkpoint and show the pass mark. Flashcards
keep term + definition: the mode of play is click-to-reveal, so the card text
is the content, not a secret.
"""

from __future__ import annotations

import uuid

from app.models.lms.course import ModuleItem


def _sanitize_quiz(content: dict) -> dict:
    return {
        "pass_threshold": content.get("pass_threshold", 0),
        "mid_video_at_seconds": content.get("mid_video_at_seconds"),
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


def _sanitize(kind: str, content: dict | None) -> dict:
    content = content or {}
    if kind == "quiz":
        return _sanitize_quiz(content)
    if kind == "text":
        return _sanitize_text(content)
    if kind == "flashcards":
        return _sanitize_flashcards(content)
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