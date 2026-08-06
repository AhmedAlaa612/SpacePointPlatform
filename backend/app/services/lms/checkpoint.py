"""Video checkpoint quiz grading (2026-08-07) — stateless, unlike quiz.py.

A checkpoint quiz gates *playback*, not module completion (the design's own
framing: "answer to keep watching") — there's no ItemProgress row to update,
no attempts/best-score tracking, nothing persisted per submission. Grading
happens directly against the checkpoint's own `content` and the result is
handed straight back. "Skip" needs no endpoint at all: the player just
resumes without ever calling this.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.course import VideoCheckpoint


async def submit_checkpoint_answer(
    db: AsyncSession, *, checkpoint_id: uuid.UUID, item_id: uuid.UUID, answer: int | list[int] | str,
) -> dict:
    checkpoint = await db.get(VideoCheckpoint, checkpoint_id)
    if checkpoint is None or checkpoint.item_id != item_id:
        raise HTTPException(404, detail="Checkpoint not found")
    if checkpoint.kind != "quiz":
        raise HTTPException(400, detail="Only quiz checkpoints take an answer")

    content = checkpoint.content or {}
    question_type = content.get("question_type")
    options = content.get("options") or []
    explanation = content.get("explanation")

    if question_type == "open":
        if not isinstance(answer, str):
            raise HTTPException(400, detail="Open questions take a text answer")
        # Not graded — a reflection prompt, recorded as answered and nothing more.
        return {"correct": None, "explanation": explanation}

    if question_type == "mcq":
        if not isinstance(answer, int) or isinstance(answer, bool) or not (0 <= answer < len(options)):
            raise HTTPException(400, detail="Answer is out of range")
        return {"correct": bool(options[answer].get("is_correct")), "explanation": explanation}

    if question_type == "multiselect":
        if not isinstance(answer, list) or not all(isinstance(a, int) and not isinstance(a, bool) for a in answer):
            raise HTTPException(400, detail="multiselect answers must be a list of option indices")
        if any(not (0 <= a < len(options)) for a in answer):
            raise HTTPException(400, detail="Answer is out of range")
        correct_set = {i for i, o in enumerate(options) if o.get("is_correct")}
        # All-or-nothing: the selected set has to match the correct set exactly.
        return {"correct": set(answer) == correct_set, "explanation": explanation}

    raise HTTPException(400, detail=f"Unknown question_type '{question_type}'")
