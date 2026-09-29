"""merge heads 4/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: 5ab82585c876
Revises: b7917ebe36f5, baseline
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = '5ab82585c876'
down_revision = ('b7917ebe36f5', 'baseline')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
