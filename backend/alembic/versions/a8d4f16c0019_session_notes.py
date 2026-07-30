"""sessions.notes — a free-text comment box on the session (I2-7 follow-up)

Operator decision, 2026-07-30: "just leave a room for a general comment, they
can input all their notes including those related to stock there, till admin
fill the data".

The job this column does is narrow and worth stating, because it is easy to
mistake for a feature. Equipment pickup (I2-7) can only offer what
`stock_levels` says is on the shelf, and until ops has walked the co-working
spaces with a clipboard that list is empty. Without somewhere to type it, an
instructor who took a mic speaker the register has never heard of has no way
to say so, and the fact is simply lost. This is that somewhere.

**One editable blob, not a comment log** — the ask was a simple text area.
The known cost is that a lead and a co-instructor editing at the same moment
can overwrite each other; accepted by the operator as the right trade for
simplicity, and mitigated only by saving on blur rather than per keystroke.

**Nothing notifies ops** (also the operator's call). Ops reads it when they
open the session.

Revision ID: a8d4f16c0019
Revises: f7c3e95b0018
Create Date: 2026-07-30
"""

import sqlalchemy as sa
from alembic import op

revision = "a8d4f16c0019"
down_revision = "f7c3e95b0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("sessions", "notes")
