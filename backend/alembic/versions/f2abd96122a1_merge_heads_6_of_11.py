"""merge heads 6/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: f2abd96122a1
Revises: 18b05c512114, e1b3d05f0036
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = 'f2abd96122a1'
down_revision = ('18b05c512114', 'e1b3d05f0036')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
