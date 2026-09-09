"""Seed the cohort knowledge-quiz question bank from a filled-in Excel file
(the boss-provided "SpacePoint_Course_100_MCQ_Question_Bank.xlsx" — 100
questions across 6 topics: Introduction to Space & Satellites, CDHS, EPS,
ADCS, Communications, Launch & Operations).

    python -m scripts.seed_cohort_quiz_questions --file /path/to/SpacePoint_Course_100_MCQ_Question_Bank.xlsx [--created-by ops@example.com] [--dry-run]

Reuses `services/lms/cohort_quiz_importer.py::parse_cohort_quiz_question_import`
and `services/lms/cohort_quiz.py::import_questions_deduped` directly — the
same parser and dedup logic the admin UI's "Import from Excel" button calls —
so this script is just the CLI equivalent of clicking Import, not a second
implementation to keep in sync.

This only loads the bank — it does NOT create a `CohortQuizTemplate`. The
100 questions are raw material; a facilitator still picks which subset (and
in what order) becomes an actual cohort-facing quiz via the admin UI, per
the operator's "same fixed set per cohort, hand-picked" decision. Building
a template from imported questions is a separate, deliberate authoring
step, not something this script should guess at.

IDEMPOTENT: skips any row whose `prompt` text already exists in the bank —
safe to re-run after the source spreadsheet is revised; it only inserts
what's new. It never edits or deletes an existing question, so a topic/
wording fix already made by hand in the admin UI is not overwritten by
re-running this with an older copy of the file.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.models.user import User  # noqa: E402
from app.services.lms.cohort_quiz import import_questions_deduped  # noqa: E402
from app.services.lms.cohort_quiz_importer import parse_cohort_quiz_question_import  # noqa: E402


async def seed_cohort_quiz_questions(
    db: AsyncSession, *, file_bytes: bytes, created_by_user_id: uuid.UUID | None,
) -> tuple[int, int, list[str]]:
    """Returns (created_count, skipped_duplicate_count, parse_errors).
    Flushes but never commits/rolls back — that's the caller's job, same
    convention as the other seed/backfill scripts in this directory."""
    parsed, parse_errors = parse_cohort_quiz_question_import(file_bytes)
    created, skipped = await import_questions_deduped(db, parsed=parsed, created_by=created_by_user_id)
    return len(created), skipped, parse_errors


async def run(file_path: str, created_by_email: str | None, dry_run: bool = False) -> None:
    from app.db.session import AsyncSessionLocal

    file_bytes = Path(file_path).read_bytes()

    async with AsyncSessionLocal() as db:
        created_by_user_id = None
        if created_by_email:
            user = (await db.execute(select(User).where(User.email == created_by_email.lower()))).scalars().first()
            if user is None:
                print(f"[seed_cohort_quiz_questions] WARNING: no user found for "
                      f"--created-by {created_by_email!r} — questions will be created with no author.")
            else:
                created_by_user_id = user.id

        created, skipped, parse_errors = await seed_cohort_quiz_questions(
            db, file_bytes=file_bytes, created_by_user_id=created_by_user_id,
        )

        if dry_run:
            await db.rollback()
            print(f"[seed_cohort_quiz_questions] DRY RUN — would add {created} question(s), "
                  f"{skipped} already present; no changes written.")
        else:
            await db.commit()
            print(f"[seed_cohort_quiz_questions] added {created} question(s), {skipped} already present.")

        if parse_errors:
            print(f"[seed_cohort_quiz_questions] SKIPPED {len(parse_errors)} row(s) from the file "
                  f"— fix and re-run to pick them up:")
            for line in parse_errors:
                print(f"  {line}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to the filled-in question-bank .xlsx")
    parser.add_argument("--created-by", default=None, help="Email of the user to attribute authorship to (optional)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.file, args.created_by, dry_run=args.dry_run))
