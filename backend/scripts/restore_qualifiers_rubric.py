"""Restore Ru'ya Qualifiers cohort rubric and criteria.

Specifically built for Ru'ya Qualifiers cohort (d651bca0-394f-4b47-9fa9-ddea274a430f).
Restores the 8 original criteria keys and repoints competition_scores to this rubric
so the breakdown display is restored.

Usage:
  # Dry-run preview:
  python scripts/restore_qualifiers_rubric.py --dry-run

  # Apply changes:
  python scripts/restore_qualifiers_rubric.py --commit
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select, update
from app.db.session import AsyncSessionLocal
from app.models.competitions.judging import (
    CompetitionRubric, CompetitionRubricCriterion, CompetitionScore,
)
from app.models.sessions.cohort import Cohort

DEFAULT_COHORT_ID = "d651bca0-394f-4b47-9fa9-ddea274a430f"

ORIGINAL_QUALIFIERS_CRITERIA = [
    ("mission_concept", "Mission Concept", 15),
    ("dashboard", "Dashboard", 15),
    ("madar_mission", "Madar Mission", 15),
    ("tinkercad_circuit", "Tinkercad Circuit", 15),
    ("tinkercad_3d_design", "Tinkercad 3D Design", 10),
    ("poster", "Poster", 10),
    ("recorded_presentation", "Recorded Presentation", 10),
    ("consistency", "Consistency", 10),
]


async def main():
    parser = argparse.ArgumentParser(description="Restore Ru'ya Qualifiers rubric and scores")
    parser.add_argument("--cohort-id", default=DEFAULT_COHORT_ID, help="Target cohort UUID")
    parser.add_argument("--commit", action="store_true", help="Apply changes (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing (default)")
    args = parser.parse_args()

    cohort_uuid = uuid.UUID(args.cohort_id)

    async with AsyncSessionLocal() as db:
        cohort = await db.get(Cohort, cohort_uuid)
        if not cohort:
            print(f"❌ Error: Cohort '{args.cohort_id}' not found.")
            sys.exit(1)

        print(f"✓ Cohort found: '{cohort.name}' (Program: {cohort.program_id})")

        # Check existing rubric for cohort
        rubric = await db.scalar(
            select(CompetitionRubric).where(CompetitionRubric.cohort_id == cohort_uuid)
        )
        if rubric is None:
            print(f"ℹ️  Creating dedicated rubric for cohort '{cohort.name}'")
            rubric = CompetitionRubric(
                id=uuid.uuid4(),
                program_id=cohort.program_id,
                cohort_id=cohort_uuid,
                name="Ru'ya Qualifiers Rubric",
            )
            db.add(rubric)
            await db.flush()
        else:
            print(f"✓ Found existing cohort rubric: '{rubric.name}' ({rubric.id})")

        # Upsert criteria
        existing_criteria = {
            c.key: c for c in (await db.execute(
                select(CompetitionRubricCriterion).where(CompetitionRubricCriterion.rubric_id == rubric.id)
            )).scalars().all()
        }

        for pos, (key, label, max_pts) in enumerate(ORIGINAL_QUALIFIERS_CRITERIA):
            if key in existing_criteria:
                crit = existing_criteria[key]
                crit.label = label
                crit.max_points = max_pts
                crit.position = pos
                crit.scored_by = "judge"
                print(f"  - Updated criterion '{key}' ({max_pts} pts)")
            else:
                crit = CompetitionRubricCriterion(
                    id=uuid.uuid4(),
                    rubric_id=rubric.id,
                    key=key,
                    label=label,
                    max_points=max_pts,
                    position=pos,
                    scored_by="judge",
                    sub_criteria=[],
                )
                db.add(crit)
                print(f"  + Added criterion '{key}' ({max_pts} pts)")

        await db.flush()

        # Update competition_scores for this cohort to point to this rubric
        score_count = (await db.execute(
            select(CompetitionScore).where(CompetitionScore.cohort_id == cohort_uuid)
        )).scalars().all()

        print(f"✓ Found {len(score_count)} competition scores in cohort.")
        for s in score_count:
            s.rubric_id = rubric.id

        # Check sibling cohorts to attach unassigned rubric
        sibling = (await db.execute(
            select(Cohort).where(
                Cohort.program_id == cohort.program_id,
                Cohort.id != cohort_uuid,
            ).order_by(Cohort.created_at.desc())
        )).scalars().first()

        if sibling:
            unassigned_rubric = await db.scalar(
                select(CompetitionRubric).where(
                    CompetitionRubric.program_id == cohort.program_id,
                    CompetitionRubric.cohort_id.is_(None),
                )
            )
            if unassigned_rubric:
                print(f"✓ Linking unassigned rubric '{unassigned_rubric.name}' to sibling cohort '{sibling.name}' ({sibling.id})")
                unassigned_rubric.cohort_id = sibling.id

        if not args.commit:
            print("\n🔍 DRY-RUN MODE: No database changes were committed.")
            print("To commit these changes, re-run with --commit.")
            return

        await db.commit()
        print(f"\n✅ SUCCESS! Restored rubric and {len(ORIGINAL_QUALIFIERS_CRITERIA)} criteria for cohort {cohort_uuid}.")


if __name__ == "__main__":
    asyncio.run(main())
