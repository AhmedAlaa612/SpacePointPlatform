"""cohort-scoped competition rubrics and restore qualifiers rubric

Revision ID: e2f3a4b5c6d7
Revises: a1b2c3d4e5f7
Create Date: 2026-10-03 18:00:00.000000
"""

import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e2f3a4b5c6d7'
down_revision = 'a1b2c3d4e5f7'
branch_labels = None
depends_on = None

QUALIFIERS_COHORT_ID = "d651bca0-394f-4b47-9fa9-ddea274a430f"
RUYA_PROGRAM_ID = "04afdd0a-8c65-46cc-a699-973bb17685bf"

ORIGINAL_QUALIFIERS_CRITERIA = [
    ("mission_concept", "Mission Concept", 15, 0),
    ("dashboard", "Dashboard", 15, 1),
    ("madar_mission", "Madar Mission", 15, 2),
    ("tinkercad_circuit", "Tinkercad Circuit", 15, 3),
    ("tinkercad_3d_design", "Tinkercad 3D Design", 10, 4),
    ("poster", "Poster", 10, 5),
    ("recorded_presentation", "Recorded Presentation", 10, 6),
    ("consistency", "Consistency", 10, 7),
]


def upgrade():
    # 1. Add cohort_id column
    op.add_column(
        'competition_rubrics',
        sa.Column('cohort_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('cohorts.id', ondelete='CASCADE'), nullable=True)
    )
    op.create_index(op.f('ix_competition_rubrics_cohort_id'), 'competition_rubrics', ['cohort_id'], unique=False)
    op.create_unique_constraint('uq_competition_rubrics_cohort_id', 'competition_rubrics', ['cohort_id'])

    # 2. Data migration / restoration
    conn = op.get_bind()

    # Check if Qualifiers cohort exists
    qualifiers_cohort = conn.execute(
        sa.text("SELECT id, program_id FROM cohorts WHERE id = :cid"),
        {"cid": QUALIFIERS_COHORT_ID}
    ).fetchone()

    if qualifiers_cohort:
        program_id = str(qualifiers_cohort[1])

        # Find or create a dedicated rubric for the Qualifiers cohort
        qual_rubric = conn.execute(
            sa.text("SELECT id FROM competition_rubrics WHERE cohort_id = :cid"),
            {"cid": QUALIFIERS_COHORT_ID}
        ).fetchone()

        if not qual_rubric:
            qual_rubric_id = str(uuid.uuid4())
            conn.execute(
                sa.text("""
                    INSERT INTO competition_rubrics (id, program_id, cohort_id, name, created_at)
                    VALUES (:id, :program_id, :cohort_id, 'Ru''ya Qualifiers Rubric', NOW())
                """),
                {
                    "id": qual_rubric_id,
                    "program_id": program_id,
                    "cohort_id": QUALIFIERS_COHORT_ID,
                }
            )
        else:
            qual_rubric_id = str(qual_rubric[0])

        # Ensure the 8 original criteria are present on the Qualifiers rubric
        for key, label, max_pts, pos in ORIGINAL_QUALIFIERS_CRITERIA:
            existing_crit = conn.execute(
                sa.text("SELECT id FROM competition_rubric_criteria WHERE rubric_id = :rid AND key = :k"),
                {"rid": qual_rubric_id, "k": key}
            ).fetchone()
            if not existing_crit:
                conn.execute(
                    sa.text("""
                        INSERT INTO competition_rubric_criteria (id, rubric_id, key, label, max_points, position, scored_by, sub_criteria)
                        VALUES (:id, :rid, :k, :label, :max_pts, :pos, 'judge', '[]'::jsonb)
                    """),
                    {
                        "id": str(uuid.uuid4()),
                        "rid": qual_rubric_id,
                        "k": key,
                        "label": label,
                        "max_pts": max_pts,
                        "pos": pos,
                    }
                )

        # Repoint competition_scores for this cohort to the Qualifiers rubric
        conn.execute(
            sa.text("""
                UPDATE competition_scores
                SET rubric_id = :rid
                WHERE cohort_id = :cid
            """),
            {"rid": qual_rubric_id, "cid": QUALIFIERS_COHORT_ID}
        )

        # Find any other sibling cohort in this program to attach the remaining unassigned rubric to
        sibling_cohort = conn.execute(
            sa.text("""
                SELECT id FROM cohorts
                WHERE program_id = :pid AND id != :cid
                ORDER BY created_at DESC LIMIT 1
            """),
            {"pid": program_id, "cid": QUALIFIERS_COHORT_ID}
        ).fetchone()

        if sibling_cohort:
            sibling_id = str(sibling_cohort[0])
            # Assign any unassigned rubric with criterion_1 (the newer rubric) to the sibling cohort
            conn.execute(
                sa.text("""
                    UPDATE competition_rubrics
                    SET cohort_id = :sid
                    WHERE program_id = :pid AND cohort_id IS NULL
                """),
                {"sid": sibling_id, "pid": program_id}
            )


def downgrade():
    op.drop_constraint('uq_competition_rubrics_cohort_id', 'competition_rubrics', type_='unique')
    op.drop_index(op.f('ix_competition_rubrics_cohort_id'), table_name='competition_rubrics')
    op.drop_column('competition_rubrics', 'cohort_id')
