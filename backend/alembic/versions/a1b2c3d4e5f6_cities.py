"""Cities — a small, admin-configurable list (2026-08-08), seeded with the
UAE cities the instructor-apply form already hardcoded
(`frontend/src/pages/instructors/apply/InstructorApply.tsx`'s `UAE_CITIES`).

Turns three previously-free-text "where" fields into structured references
against the same table, so staffing can match "instructor open to work in
city X" against "location is in city X" by exact id instead of comparing
two independently hand-typed strings:

- `locations.city_id` (new, nullable — left unset on existing rows; guessing
  a city from `Location.name` would be actively wrong, e.g. "Main UAE" or
  "Egypt" aren't cities. Ops fills it in going forward.)
- `users.city_id` (new, nullable — a student's/staff member's own city,
  independent of the Contact spine's free-text city, same precedent as
  `users.country` already being its own copy)
- `applicant_profiles.deliver_city_ids` / `city_of_residence_id` (new,
  **replacing** the old `deliver_cities`/`city_of_residence` string
  columns) — backfilled below by case-insensitive matching against the
  newly-seeded cities before the old columns are dropped, so no existing
  applicant's data is silently lost.

Revision ID: a1b2c3d4e5f6
Revises: 3f4f7d1237e1
Create Date: 2026-08-08
"""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "3f4f7d1237e1"
branch_labels = None
depends_on = None

_UAE_CITIES = ["Dubai", "Abu Dhabi", "Sharjah", "Al Ain", "Ajman", "Umm Al Quwain", "Fujairah", "Ras Al Khaimah"]


def upgrade() -> None:
    op.create_table(
        "cities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("country", "name", name="uq_cities_country_name"),
    )

    connection = op.get_bind()
    connection.execute(
        sa.text("INSERT INTO cities (id, name, country, is_active) VALUES (:id, :name, 'AE', true)"),
        [{"id": str(uuid.uuid4()), "name": name} for name in _UAE_CITIES],
    )

    op.add_column("locations", sa.Column("city_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_locations_city_id", "locations", "cities", ["city_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_locations_city_id", "locations", ["city_id"])

    op.add_column("users", sa.Column("city_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_users_city_id", "users", "cities", ["city_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_users_city_id", "users", ["city_id"])

    # ── applicant_profiles: add structured columns, backfill, drop the old ──
    op.add_column("applicant_profiles", sa.Column("city_of_residence_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_applicant_profiles_city_of_residence_id", "applicant_profiles", "cities",
        ["city_of_residence_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column("applicant_profiles", sa.Column("deliver_city_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True))

    connection.execute(sa.text(
        "UPDATE applicant_profiles ap SET city_of_residence_id = c.id "
        "FROM cities c "
        "WHERE c.country = 'AE' AND lower(trim(c.name)) = lower(trim(ap.city_of_residence))"
    ))
    connection.execute(sa.text(
        "UPDATE applicant_profiles ap SET deliver_city_ids = sub.city_ids "
        "FROM ("
        "  SELECT ap2.user_id, array_agg(DISTINCT c.id) AS city_ids "
        "  FROM applicant_profiles ap2 "
        "  CROSS JOIN LATERAL unnest(ap2.deliver_cities) AS dc(city_name) "
        "  JOIN cities c ON c.country = 'AE' AND lower(trim(c.name)) = lower(trim(dc.city_name)) "
        "  WHERE ap2.deliver_cities IS NOT NULL "
        "  GROUP BY ap2.user_id"
        ") sub "
        "WHERE ap.user_id = sub.user_id"
    ))

    op.drop_column("applicant_profiles", "city_of_residence")
    op.drop_column("applicant_profiles", "deliver_cities")


def downgrade() -> None:
    op.add_column("applicant_profiles", sa.Column("deliver_cities", postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column("applicant_profiles", sa.Column("city_of_residence", sa.String(100), nullable=True))

    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE applicant_profiles ap SET city_of_residence = c.name "
        "FROM cities c WHERE c.id = ap.city_of_residence_id"
    ))
    connection.execute(sa.text(
        "UPDATE applicant_profiles ap SET deliver_cities = sub.names "
        "FROM ("
        "  SELECT ap2.user_id, array_agg(c.name) AS names "
        "  FROM applicant_profiles ap2 "
        "  CROSS JOIN LATERAL unnest(ap2.deliver_city_ids) AS dci(city_id) "
        "  JOIN cities c ON c.id = dci.city_id "
        "  WHERE ap2.deliver_city_ids IS NOT NULL "
        "  GROUP BY ap2.user_id"
        ") sub "
        "WHERE ap.user_id = sub.user_id"
    ))

    op.drop_constraint("fk_applicant_profiles_city_of_residence_id", "applicant_profiles", type_="foreignkey")
    op.drop_column("applicant_profiles", "city_of_residence_id")
    op.drop_column("applicant_profiles", "deliver_city_ids")

    op.drop_index("ix_users_city_id", table_name="users")
    op.drop_constraint("fk_users_city_id", "users", type_="foreignkey")
    op.drop_column("users", "city_id")

    op.drop_index("ix_locations_city_id", table_name="locations")
    op.drop_constraint("fk_locations_city_id", "locations", type_="foreignkey")
    op.drop_column("locations", "city_id")

    op.drop_table("cities")
