"""UNIQUE(users.contact_id) — D1 (LMS Phase 2 Stage 1, 2026-08-10).

**One account per contact**, per the operator's 2026-08-10 decision
(PHASE2_EXECUTION_PLAN.md §2 D1). This is the load-bearing migration the
audit (LMS_DESIGN_AUDIT.md §9.3(a)) warned a bare `ADD CONSTRAINT` would
fail outright against on production: merges have already happened there, and
any duplicate is a human decision (which account survives) that a migration
must never make silently.

So this migration checks for duplicates itself before attempting the
constraint, and refuses loudly and specifically (not a raw
`UniqueViolation`) if it finds any — rather than requiring whoever runs
`alembic upgrade head` to have separately run the audit's preflight query
first. **If this migration refuses:** resolve each reported contact_id via
the merge-review flow (`services/spine/identity.py::merge_contacts` now
special-cases the `users` FK for exactly this — see that function's
docstring) before re-running.

Confirmed zero duplicates on `spacepoint_dev`/`spacepoint_test` (bugs.md
B4: "9 users, 7 with contacts") — that says nothing about production, which
is exactly the audit's point.

The `ix_users_contact_id` standalone index from `7d448f6873a9` becomes
redundant once this lands (Postgres backs a UNIQUE constraint with its own
index) — dropped here rather than left for someone to rediscover later
(audit §9.3(b)).
"""

from alembic import op
import sqlalchemy as sa

revision = "efeef0a62c62"
down_revision = "8e7ff566e539"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    duplicates = conn.execute(sa.text("""
        SELECT contact_id, count(*) AS accounts, array_agg(email ORDER BY created_at) AS emails
        FROM users WHERE contact_id IS NOT NULL
        GROUP BY contact_id HAVING count(*) > 1
    """)).fetchall()

    if duplicates:
        lines = "\n".join(
            f"  contact_id={row.contact_id}  accounts={row.accounts}  emails={row.emails}"
            for row in duplicates
        )
        raise RuntimeError(
            "D1 migration refused: the following contacts hold more than one user account.\n"
            f"{lines}\n"
            "Each is a human decision (which account survives) — resolve via the merge-review "
            "flow (merge_contacts now special-cases this and files a 'dual_lms_accounts' "
            "merge_reviews row for exactly this shape) before re-running this migration. "
            "See LMS_DESIGN_AUDIT.md §9.3(a)."
        )

    op.drop_index("ix_users_contact_id", table_name="users")
    op.create_unique_constraint("uq_users_contact_id", "users", ["contact_id"])


def downgrade() -> None:
    op.drop_constraint("uq_users_contact_id", "users", type_="unique")
    op.create_index("ix_users_contact_id", "users", ["contact_id"])
