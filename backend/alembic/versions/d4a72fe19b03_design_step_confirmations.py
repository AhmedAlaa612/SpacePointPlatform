"""Design step self-check confirmations (2026-09) — one additive column on
`designs`.

Closes a gap in the Roadmap board redesign: a Madar `mission_run` checklist
item is "auto-tracked" (services/lms/program.py's `_mission_run_item_done`)
purely off the step's own `is_valid` math, so it used to flip to done the
instant the bare-minimum requirement was met (e.g. one component added) —
before the student had actually finished shopping/tuning that step.
`confirmed_steps` is the persisted record of the student's own explicit
"Complete this step" click (DesignMissionPage.tsx) for each design-phase
step key (`setup` plus the 8 selectable `DESIGN_STEP_LABELS` keys minus
`downlink`, which isn't a tab of its own); `report` is deliberately never a
member — it stays purely validity-driven, matching the frontend's own
exclusion of the Report tab from the Complete-button flow. A step's
checklist item now reads done only once BOTH `is_valid` and the step's key
are in this list — see `_mission_run_item_done`'s updated logic.

Revision ID: d4a72fe19b03
Revises: a3f6d18c5b02
Create Date: 2026-09-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'd4a72fe19b03'
down_revision: Union[str, None] = 'a3f6d18c5b02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'designs',
        sa.Column(
            'confirmed_steps', postgresql.JSONB(astext_type=sa.Text()),
            nullable=False, server_default='[]',
        ),
    )


def downgrade() -> None:
    op.drop_column('designs', 'confirmed_steps')
