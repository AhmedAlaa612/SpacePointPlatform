"""merge heads 3/11 (2026-09-30)

Binary merge step — alembic cannot execute an N-way merge (it crashes in
head bookkeeping), so the fragmented tips are unified pairwise. Empty:
no schema change.

Revision ID: b7917ebe36f5
Revises: b68ce2b52a57, b2d8a91c0002
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = 'b7917ebe36f5'
down_revision = ('b68ce2b52a57', 'b2d8a91c0002')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
