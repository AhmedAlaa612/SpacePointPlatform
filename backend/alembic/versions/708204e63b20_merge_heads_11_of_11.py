"""merge heads 11/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: 708204e63b20
Revises: 19bff391f7a7, 3c283ec9a24c
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = '708204e63b20'
down_revision = ('19bff391f7a7', '3c283ec9a24c')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
