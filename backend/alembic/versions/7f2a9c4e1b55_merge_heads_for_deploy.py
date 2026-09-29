"""merge fragmented heads into one (2026-09-30)

The versions directory accumulated one head per feature branch, so
`alembic upgrade head` — what the deploy pipeline runs — aborts with
"Multiple head revisions are present" and the deploy rolls back before
anything is committed. This empty merge unifies every head into a single
`head` again without touching any schema: all real migrations still run
in dependency order underneath it.

Revision ID: 7f2a9c4e1b55
Revises: 8b3d0f61a2c7, 9a46ca83d607, a4c1e93f0044, b2d8a91c0002, baseline, c4d9e2f6a813, e1b3d05f0036, e7c4a92d0036, e8a85d1c464b, f3a7c1d8e942, f6b3d94e1157, 3c283ec9a24c
Create Date: 2026-09-30 00:00:00.000000

"""

# revision identifiers, used by Alembic.
revision = '7f2a9c4e1b55'
down_revision = (
    '8b3d0f61a2c7',
    '9a46ca83d607',
    'a4c1e93f0044',
    'b2d8a91c0002',
    'baseline',
    'c4d9e2f6a813',
    'e1b3d05f0036',
    'e7c4a92d0036',
    'e8a85d1c464b',
    'f3a7c1d8e942',
    'f6b3d94e1157',
    '3c283ec9a24c',
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
