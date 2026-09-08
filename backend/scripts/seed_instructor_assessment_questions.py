"""Seed the real instructor scenario-assessment question bank from the
boss-provided Excel file ("SpacePoint__Instructor_Scenario_Assessment.xlsx" —
71 scenarios across 13 categories, ~18 flagged critical).

    python -m scripts.seed_instructor_assessment_questions --file /path/to/SpacePoint__Instructor_Scenario_Assessment.xlsx [--config-name "Shallow Flight Instructor Assessment"] [--created-by ops@example.com] [--dry-run]

Reuses `services/instructor_assessment/importer.py::parse_assessment_question_import`
directly — the exact same parser the admin UI's "Import from Excel" button
calls — so this script is just the CLI equivalent of get-or-create the config,
then click Import, rather than a second implementation to keep in sync.

IDEMPOTENT: get-or-creates the `AssessmentConfig` by exact `name` match, and
within it skips any row whose `prompt` text already exists — safe to re-run
after the boss revises the spreadsheet and adds a few rows; it only inserts
what's new. It never edits or deletes an existing question, so a
category/wording fix already made by hand in the admin UI is not overwritten
by re-running this with an older copy of the file.
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

from app.models.instructor_assessment.config import AssessmentConfig, AssessmentQuestion  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.instructor_assessment.importer import parse_assessment_question_import  # noqa: E402


async def seed_instructor_assessment_questions(
    db: AsyncSession, *, file_bytes: bytes, config_name: str, created_by_user_id: uuid.UUID | None,
) -> tuple[AssessmentConfig, bool, int, int, list[str]]:
    """Returns (config, config_is_new, created_count, skipped_duplicate_count,
    parse_errors). Flushes but never commits/rolls back — that's the caller's
    job, same convention as the other seed/backfill scripts in this
    directory."""
    parsed, parse_errors = parse_assessment_question_import(file_bytes)

    config = (await db.execute(
        select(AssessmentConfig).where(AssessmentConfig.name == config_name)
    )).scalars().first()
    config_is_new = config is None
    if config is None:
        config = AssessmentConfig(id=uuid.uuid4(), name=config_name, created_by=created_by_user_id)
        db.add(config)
        await db.flush()

    existing_prompts = set((await db.execute(
        select(AssessmentQuestion.prompt).where(AssessmentQuestion.config_id == config.id)
    )).scalars().all())

    created = 0
    skipped = 0
    for q in parsed:
        if q.prompt in existing_prompts:
            skipped += 1
            continue
        db.add(AssessmentQuestion(
            id=uuid.uuid4(), config_id=config.id, category=q.category, prompt=q.prompt,
            options=[o.model_dump() for o in q.options], critical=q.critical, rationale=q.rationale,
        ))
        existing_prompts.add(q.prompt)
        created += 1

    await db.flush()
    return config, config_is_new, created, skipped, parse_errors


async def run(file_path: str, config_name: str, created_by_email: str | None, dry_run: bool = False) -> None:
    from app.db.session import AsyncSessionLocal

    file_bytes = Path(file_path).read_bytes()

    async with AsyncSessionLocal() as db:
        created_by_user_id = None
        if created_by_email:
            user = (await db.execute(select(User).where(User.email == created_by_email.lower()))).scalars().first()
            if user is None:
                print(f"[seed_instructor_assessment_questions] WARNING: no user found for "
                      f"--created-by {created_by_email!r} — config will be created with no author.")
            else:
                created_by_user_id = user.id

        config, config_is_new, created, skipped, parse_errors = await seed_instructor_assessment_questions(
            db, file_bytes=file_bytes, config_name=config_name, created_by_user_id=created_by_user_id,
        )
        config_note = "new config" if config_is_new else "existing config"

        if dry_run:
            await db.rollback()
            print(f"[seed_instructor_assessment_questions] DRY RUN — {config_note} {config_name!r}: "
                  f"would add {created} question(s), {skipped} already present; no changes written.")
        else:
            await db.commit()
            print(f"[seed_instructor_assessment_questions] {config_note} {config_name!r}: "
                  f"added {created} question(s), {skipped} already present.")

        if parse_errors:
            print(f"[seed_instructor_assessment_questions] SKIPPED {len(parse_errors)} row(s) from the file "
                  f"— fix and re-run to pick them up:")
            for line in parse_errors:
                print(f"  {line}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Path to the filled-in question-bank .xlsx")
    parser.add_argument(
        "--config-name", default="Shallow Flight Instructor Assessment",
        help="Name of the AssessmentConfig to create/add into (default: %(default)s)",
    )
    parser.add_argument("--created-by", default=None, help="Email of the user to attribute authorship to (optional)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.file, args.config_name, args.created_by, dry_run=args.dry_run))
