"""Competition scores: separate autosaved draft from deliberate submit (2026-08-27)

A judge's score row was "scored" the moment it existed, which is exactly
what let a team's page merely being opened (the old debounced autosave)
mark it done with nothing actually judged. The fix keeps autosave —
judges do want a draft remembered across sessions — but needs a way to
tell "has a draft" apart from "the judge clicked submit". `submitted`
is that flag: defaults False on every autosaved write, set True only by
the explicit submit action, and ratcheted forward only (see
`services/competitions/judging.py::submit_score`) so revising an already-
submitted score can't accidentally un-score it. `scored_team_ids`,
`leaderboard`, and `list_judges_with_progress` all read this flag now
instead of row existence.

Revision ID: c7d2e8a94f5b
Revises: a3f9b6e1d4c2
"""

import sqlalchemy as sa
from alembic import op

revision = "c7d2e8a94f5b"
down_revision = "a3f9b6e1d4c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "competition_scores",
        sa.Column("submitted", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("competition_scores", "submitted")
