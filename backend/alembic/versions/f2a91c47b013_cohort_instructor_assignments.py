"""Cohort instructor assignments, cohort-call interest, and a global role rate

Operator decisions, 2026-08-24 (WhatsApp + the SpacePoint Workshop Operations
Process doc). Three related pieces of the same change: staffing an instructor
is a *cohort* commitment, not five independent session offers.

`cohort_instructor_assignments` records the deal — one role for the whole
cohort, plus the rate that was agreed when ops picked them. **This reopens the
boundary closed on 2026-07-24**, when `cohort_instructors` was dropped in
`e5a2c93f0005` for never having been wired to anything. See the model's
docstring (`app/models/sessions/cohort_assignment.py`) for the three reasons it
comes back and, more importantly, for what it is *not*: it is not a second
source of truth for staffing state. `Session.staffing_status`, `fully_staffed`
and `session_instructors` stay authoritative for who teaches which day. The
table is deliberately named differently from `cohort_instructors` so that
`e5a2c93f0005`'s downgrade, which recreates that table, can never collide.

The unique key is `(cohort_id, user_id, role_id)` rather than
`(cohort_id, user_id)` on purpose. The one-role-per-cohort rule the operator
confirmed is enforced in the service layer for *new* selections, where it can
return a readable 409; the constraint is looser so that the backfill below can
represent pre-existing production data honestly — an instructor who really did
hold two roles across one cohort's sessions becomes two rows (which then pay
out as two correct lines) instead of failing the migration or being silently
collapsed into one.

`cohort_call_interests` is the instructor's answer to a cohort-wide call: one
role, one cover letter, and the §2 support questions (transport, ops support,
travelling from another city, free-text concerns), stated once for the cohort.
Per-session `instructor_interests` rows are still written for the ticked
sessions, so nothing already built on them changes.

`delivery_roles.default_rate_aed` is the global tier of the rate hierarchy —
session opening -> cohort opening -> role default, first non-NULL wins, the
same override-not-merge shape `resolve_duration` uses for hours. One column on
a table ops already edits at /operations/delivery-settings, rather than a new
table or a `portal_settings` string that would need parsing.

Revision ID: f2a91c47b013
Revises: c7d2e8a94f5b
Create Date: 2026-08-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "f2a91c47b013"
down_revision = "c7d2e8a94f5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("delivery_roles", sa.Column("default_rate_aed", sa.Numeric(10, 2), nullable=True))

    op.create_table(
        "cohort_instructor_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "role_id", UUID(as_uuid=True), sa.ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("rate_basis", sa.String(16), nullable=False, server_default="per_session"),
        sa.Column("rate_aed", sa.Numeric(10, 2), nullable=True),
        sa.Column("flat_amount_aed", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("source", sa.String(16), nullable=False, server_default="call"),
        sa.Column(
            "cohort_call_id", UUID(as_uuid=True), sa.ForeignKey("cohort_calls.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cohort_id", "user_id", "role_id", name="uq_cohort_instructor_assignment"),
    )
    op.create_index(
        "ix_cohort_instructor_assignments_cohort_id", "cohort_instructor_assignments", ["cohort_id"]
    )
    op.create_index(
        "ix_cohort_instructor_assignments_user_id", "cohort_instructor_assignments", ["user_id"]
    )

    op.create_table(
        "cohort_call_interests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cohort_call_id", UUID(as_uuid=True), sa.ForeignKey("cohort_calls.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("cohort_id", UUID(as_uuid=True), sa.ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "role_id", UUID(as_uuid=True), sa.ForeignKey("delivery_roles.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("needs_transport", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("needs_ops_support", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("travelling_from_other_city", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("concerns", sa.Text(), nullable=True),
        sa.Column("responsibilities_accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responsibilities_version", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("cohort_call_id", "user_id", name="uq_cohort_call_interest"),
    )
    op.create_index("ix_cohort_call_interests_cohort_call_id", "cohort_call_interests", ["cohort_call_id"])
    op.create_index("ix_cohort_call_interests_cohort_id", "cohort_call_interests", ["cohort_id"])
    op.create_index("ix_cohort_call_interests_user_id", "cohort_call_interests", ["user_id"])

    # ── Backfill ────────────────────────────────────────────────────────────
    # Every existing (cohort, instructor, role) triple that already has session
    # assignments becomes an assignment row, so instructors staffed before this
    # table existed still produce cohort payment lines. `source='direct'`
    # because none of them came through a cohort call, and `rate_aed` stays
    # NULL because no rate was ever recorded for them — the payment line
    # resolves one live in that case, exactly as it does today. Grouping by
    # role_id (not just user) is what lets a legacy mixed-role cohort survive
    # the unique constraint; see this file's docstring.
    op.execute(
        """
        INSERT INTO cohort_instructor_assignments
            (id, cohort_id, user_id, role_id, rate_basis, status, source, created_at)
        SELECT gen_random_uuid(), s.cohort_id, si.user_id, si.role_id,
               'per_session', 'active', 'direct', NOW()
        FROM session_instructors si
        JOIN sessions s ON s.id = si.session_id
        GROUP BY s.cohort_id, si.user_id, si.role_id
        """
    )

    # Anyone who backfilled into more than one row held two roles inside a
    # single cohort — legitimate historically, but no longer allowed for new
    # selections. Print them rather than collapsing them silently, so whoever
    # runs this can see who is affected before the rule starts biting.
    mixed = op.get_bind().execute(
        sa.text(
            """
            SELECT c.name AS cohort, u.full_name, count(*) AS roles
            FROM cohort_instructor_assignments a
            JOIN cohorts c ON c.id = a.cohort_id
            JOIN users u ON u.id = a.user_id
            GROUP BY c.name, u.full_name
            HAVING count(*) > 1
            ORDER BY c.name, u.full_name
            """
        )
    ).fetchall()
    if mixed:
        print(
            f"[f2a91c47b013] {len(mixed)} instructor/cohort pair(s) held more than one "
            "role in the same cohort and were backfilled as separate assignment rows:"
        )
        for cohort, name, roles in mixed:
            print(f"    - {name} in {cohort}: {roles} roles")


def downgrade() -> None:
    op.drop_index("ix_cohort_call_interests_user_id", table_name="cohort_call_interests")
    op.drop_index("ix_cohort_call_interests_cohort_id", table_name="cohort_call_interests")
    op.drop_index("ix_cohort_call_interests_cohort_call_id", table_name="cohort_call_interests")
    op.drop_table("cohort_call_interests")

    op.drop_index("ix_cohort_instructor_assignments_user_id", table_name="cohort_instructor_assignments")
    op.drop_index("ix_cohort_instructor_assignments_cohort_id", table_name="cohort_instructor_assignments")
    op.drop_table("cohort_instructor_assignments")

    op.drop_column("delivery_roles", "default_rate_aed")
