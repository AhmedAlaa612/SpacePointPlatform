"""merge heads 8/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: 581e1d47816f
Revises: ffec2dba7cdb, e8a85d1c464b
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = '581e1d47816f'
down_revision = ('ffec2dba7cdb', 'e8a85d1c464b')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
