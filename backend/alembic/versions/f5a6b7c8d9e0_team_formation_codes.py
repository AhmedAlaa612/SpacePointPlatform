"""team formation codes + max team size

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-10-07
"""

import secrets
import string

from alembic import op
import sqlalchemy as sa


revision = 'f5a6b7c8d9e0'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _gen_code() -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


def upgrade() -> None:
    op.add_column('learner_teams', sa.Column('join_code', sa.String(length=16), nullable=True))
    op.add_column('lms_program_items', sa.Column('max_team_size', sa.Integer(), nullable=True))

    # Backfill join codes for cohort-scoped teams that lack one.
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, cohort_id FROM learner_teams WHERE cohort_id IS NOT NULL AND join_code IS NULL"
    )).fetchall()
    # Track used codes per cohort to avoid collisions within this backfill.
    used: dict[str, set[str]] = {}
    existing = conn.execute(sa.text(
        "SELECT cohort_id, join_code FROM learner_teams WHERE join_code IS NOT NULL AND cohort_id IS NOT NULL"
    )).fetchall()
    for cohort_id, code in existing:
        used.setdefault(str(cohort_id), set()).add(code)
    for team_id, cohort_id in rows:
        pool = used.setdefault(str(cohort_id), set())
        for _ in range(50):
            code = _gen_code()
            if code not in pool:
                break
        else:
            raise RuntimeError("Could not generate unique team join code")
        pool.add(code)
        conn.execute(
            sa.text("UPDATE learner_teams SET join_code = :code WHERE id = :id"),
            {"code": code, "id": str(team_id)},
        )

    op.create_unique_constraint(
        'uq_learner_teams_cohort_join_code', 'learner_teams', ['cohort_id', 'join_code'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_learner_teams_cohort_join_code', 'learner_teams', type_='unique')
    op.drop_column('lms_program_items', 'max_team_size')
    op.drop_column('learner_teams', 'join_code')
