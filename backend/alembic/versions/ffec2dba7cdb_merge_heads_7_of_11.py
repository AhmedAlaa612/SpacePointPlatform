"""merge heads 7/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: ffec2dba7cdb
Revises: f2abd96122a1, e7c4a92d0036
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = 'ffec2dba7cdb'
down_revision = ('f2abd96122a1', 'e7c4a92d0036')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
