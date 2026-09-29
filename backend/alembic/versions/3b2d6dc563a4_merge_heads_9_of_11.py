"""merge heads 9/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: 3b2d6dc563a4
Revises: 581e1d47816f, f3a7c1d8e942
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = '3b2d6dc563a4'
down_revision = ('581e1d47816f', 'f3a7c1d8e942')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
