"""merge heads 5/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: 18b05c512114
Revises: 5ab82585c876, c4d9e2f6a813
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = '18b05c512114'
down_revision = ('5ab82585c876', 'c4d9e2f6a813')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
