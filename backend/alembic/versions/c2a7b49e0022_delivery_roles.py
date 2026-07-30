"""delivery_roles — one vocabulary for who did what (I5-3)

Staffing said `lead|co`. Payment letters said "Lead Facilitator" /
"Facilitator" / "Assistant Facilitator", as a Postgres enum. The bridge
between them had no honest mapping — `co` is not the same claim as
"Facilitator", and choosing one silently would have printed a word on a
signed document that nobody had agreed to. Making roles data removes the
problem rather than papering over it.

**This migration remaps live rows; it does not assume an empty table.**
Production holds real `session_instructors` with `role` in (`lead`, `co`).
The order is: create the table, seed the three roles, add `role_id` as
nullable, backfill it (`lead` → Lead Facilitator, `co` → Facilitator, and
anything unexpected → Facilitator so the NOT NULL below cannot fail on a
value nobody predicted), *then* tighten to NOT NULL and drop the old column.

`payment_sessions.role` becomes VARCHAR(64), holding the role name at the
time. **Deliberately not an FK:** a signed letter must keep saying what it
said even if someone renames a role two years later. Documents freeze; live
assignments don't. The `payment_session_role` enum type is left in place —
dropping a type is irreversible in practice and it costs nothing to keep.

`ondelete="RESTRICT"` on `session_instructors.role_id`: a role that has ever
been assigned is part of the record. Deactivate it instead.

Revision ID: c2a7b49e0022
Revises: c1b5d27f0021
Create Date: 2026-07-30
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "c2a7b49e0022"
down_revision = "c1b5d27f0021"
branch_labels = None
depends_on = None

# Seeded here rather than in a seed script because `session_instructors.role_id`
# is NOT NULL and the backfill below cannot run without them. Reference data
# that a schema change depends on has to travel with the schema change.
SEEDED = [
    ("Lead Facilitator", 1),
    ("Facilitator", 2),
    ("Assistant Facilitator", 3),
]


def upgrade() -> None:
    op.create_table(
        "delivery_roles",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False, unique=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    role_ids = {name: uuid.uuid4() for name, _ in SEEDED}
    conn = op.get_bind()
    for name, order in SEEDED:
        conn.execute(
            sa.text(
                "INSERT INTO delivery_roles (id, name, sort_order, is_active) "
                "VALUES (:id, :name, :sort_order, true)"
            ),
            {"id": role_ids[name], "name": name, "sort_order": order},
        )

    op.add_column(
        "session_instructors",
        sa.Column("role_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )

    # `lead` → Lead Facilitator; everything else → Facilitator. The catch-all
    # is deliberate: NOT NULL below must not fail on a value nobody predicted.
    conn.execute(
        sa.text("UPDATE session_instructors SET role_id = :lead WHERE role = 'lead'"),
        {"lead": role_ids["Lead Facilitator"]},
    )
    conn.execute(
        sa.text("UPDATE session_instructors SET role_id = :fac WHERE role_id IS NULL"),
        {"fac": role_ids["Facilitator"]},
    )

    op.alter_column("session_instructors", "role_id", nullable=False)
    op.create_foreign_key(
        "fk_session_instructors_role_id", "session_instructors", "delivery_roles",
        ["role_id"], ["id"], ondelete="RESTRICT",
    )
    op.drop_column("session_instructors", "role")

    # Enum → text. USING is required; Postgres will not cast implicitly.
    op.execute(
        "ALTER TABLE payment_sessions ALTER COLUMN role TYPE VARCHAR(64) USING role::text"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE payment_sessions ALTER COLUMN role TYPE payment_session_role "
        "USING role::payment_session_role"
    )
    op.add_column(
        "session_instructors",
        sa.Column("role", sa.String(16), nullable=False, server_default="lead"),
    )
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE session_instructors si SET role = CASE "
        "WHEN dr.name = 'Lead Facilitator' THEN 'lead' ELSE 'co' END "
        "FROM delivery_roles dr WHERE dr.id = si.role_id"
    ))
    op.drop_constraint("fk_session_instructors_role_id", "session_instructors", type_="foreignkey")
    op.drop_column("session_instructors", "role_id")
    op.drop_table("delivery_roles")
