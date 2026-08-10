"""Per-account login lockout columns (B6, LMS Phase 2 Stage 0, 2026-08-10).

`/auth/login` had no rate limiting at all — the existing brake in
core/rate_limit.py is deliberately generous (1000 req/min/IP, because a
whole school shares one IP) and is the wrong tool for password guessing.
These two columns back a per-account attempt counter instead: incremented on
a failed login, reset on success, and a lockout window once the count
crosses the threshold — checked before the password itself, so a locked
account can't be probed during its window.

Hand-written (see 7d448f6873a9's docstring for why autogenerate isn't used
against this schema).
"""

import sqlalchemy as sa
from alembic import op

revision = "8e7ff566e539"
down_revision = "7d448f6873a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
