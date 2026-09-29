"""merge heads 10/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: 19bff391f7a7
Revises: 3b2d6dc563a4, f6b3d94e1157
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = '19bff391f7a7'
down_revision = ('3b2d6dc563a4', 'f6b3d94e1157')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
