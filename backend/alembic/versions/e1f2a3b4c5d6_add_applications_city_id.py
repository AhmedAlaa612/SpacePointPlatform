"""Add `applications.city_id` (2026-08-08, chained after the locations→city
soft-deprecate).

The apply form (intern / ambassador / teacher / facilitator) grows a city
picker gated by the selected country — same `cities` table `users.city_id`
and `ApplicantProfile.city_of_residence_id` use. Column is nullable: every
legacy application has no city, and a country with no SpacePoint cities
means "no city select at all", so most rows stay NULL.

`country` on the row stays as the free-text display name.
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column("city_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_applications_city_id_cities", "applications", "cities",
        ["city_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_applications_city_id_cities", "applications", type_="foreignkey")
    op.drop_column("applications", "city_id")