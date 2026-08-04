"""add 'student' to user_role enum — LMS phase 1 (LM0-2)

Students are first-class `users` rows with a `student` role, linked to the spine
via `users.contact_id` (LMS D4). This is what makes "add student to cohort →
create LMS account" work off one identity instead of two.

`student` is NOT an ops account. `require_operations` must reject it, and
`operationsLayoutRoute` must not admit it — the negative space is the point of
the role (the I3-1 lesson: a role that can reach a page but must not is
invisible until someone walks the UI as that role).

Access to course content is gated by `enrollments`, not by this role (LMS D8).
The role only says "this account is a learner surface"; it grants nothing on
its own.

Revision ID: c7e2b41a0039
Revises: d1e4c73f0038
Create Date: 2026-08-04
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c7e2b41a0039"
down_revision = "d1e4c73f0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    # Same pattern as b2d8a91c0002 ('operations') and c4f9b25e0015
    # ('coo'/'storekeeper').
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'student'")


def downgrade() -> None:
    # Postgres cannot drop a value from an enum type — no-op by design.
    pass
