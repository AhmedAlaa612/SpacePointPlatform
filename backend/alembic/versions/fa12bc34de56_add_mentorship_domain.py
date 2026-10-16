"""add mentorship domain (satellite & space mentors)

Creates tables:
- mentor_domains (Ops-managed space taxonomy tags)
- mentor_profiles (Mentors, bio, satellite missions, Option A Meet link, status, is_active)
- mentor_profile_domains (Many-to-many association)
- mentor_availabilities (Weekly & ad-hoc slots)
- mentor_bookings (Sessions & inquiries with attendance telemetry & cancellation)

Unique index:
- idx_mentor_booking_slot: Prevents double-booking same mentor at same time.

Revision ID: fa12bc34de56
Revises: e1e2f3a4b5c7
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "fa12bc34de56"
down_revision = "e1e2f3a4b5c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add 'mentor' to user_role enum
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'mentor'")

    # 2. mentor_domains (Ops-managed tags)
    op.create_table(
        "mentor_domains",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_mentor_domains_slug", "mentor_domains", ["slug"])

    # 3. mentor_profiles
    op.create_table(
        "mentor_profiles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("slug", sa.String(length=100), nullable=False, unique=True),
        sa.Column("headline", sa.String(length=255), nullable=True),
        sa.Column("company", sa.String(length=150), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column("missions_history", sa.Text(), nullable=True),
        sa.Column("contact_mode", sa.String(length=20), nullable=False, server_default="email"),
        sa.Column("google_meet_url", sa.String(length=500), nullable=True),
        sa.Column("google_refresh_token", sa.Text(), nullable=True),
        sa.Column("google_calendar_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="applied"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("session_duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("total_completed_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_sessions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_mentor_profiles_slug", "mentor_profiles", ["slug"])
    op.create_index("ix_mentor_profiles_user_id", "mentor_profiles", ["user_id"])

    # 4. mentor_profile_domains (Many-to-Many association)
    op.create_table(
        "mentor_profile_domains",
        sa.Column("mentor_id", UUID(as_uuid=True), sa.ForeignKey("mentor_profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("domain_id", UUID(as_uuid=True), sa.ForeignKey("mentor_domains.id", ondelete="CASCADE"), primary_key=True),
    )

    # 5. mentor_availabilities
    op.create_table(
        "mentor_availabilities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("mentor_id", UUID(as_uuid=True), sa.ForeignKey("mentor_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_of_week", sa.Integer(), nullable=True),
        sa.Column("specific_date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(length=50), nullable=False, server_default="UTC"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("ix_mentor_availabilities_mentor_id", "mentor_availabilities", ["mentor_id"])

    # 6. mentor_bookings
    op.create_table(
        "mentor_bookings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("mentor_id", UUID(as_uuid=True), sa.ForeignKey("mentor_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mentee_name", sa.String(length=150), nullable=False),
        sa.Column("mentee_email", sa.String(length=255), nullable=False),
        sa.Column("topics", sa.Text(), nullable=False),
        sa.Column("booking_type", sa.String(length=20), nullable=False, server_default="session"),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("google_event_id", sa.String(length=255), nullable=True),
        sa.Column("google_meet_url", sa.String(length=500), nullable=True),
        sa.Column("gateway_token", sa.String(length=64), nullable=True, unique=True),
        sa.Column("cancel_token", sa.String(length=64), nullable=True, unique=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"),
        sa.Column("mentor_joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mentee_joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_mentor_bookings_mentor_id", "mentor_bookings", ["mentor_id"])
    op.create_index("ix_mentor_bookings_gateway_token", "mentor_bookings", ["gateway_token"])
    op.create_index("ix_mentor_bookings_cancel_token", "mentor_bookings", ["cancel_token"])

    # Double-booking guard
    op.create_index(
        "idx_mentor_booking_slot",
        "mentor_bookings",
        ["mentor_id", "scheduled_start"],
        unique=True,
        postgresql_where=sa.text("status != 'cancelled' AND scheduled_start IS NOT NULL"),
    )

    # 7. Seed initial Ops space domain tags if table is empty
    initial_domains = [
        ("CubeSats & SmallSats", "cubesats-smallsats", "Spacecraft & Mission", 1),
        ("RF & Ground Stations", "rf-ground-stations", "Communications", 2),
        ("ADCS & Astrodynamics", "adcs-astrodynamics", "Flight Dynamics", 3),
        ("Optical & Payloads", "optical-payloads", "Payloads", 4),
        ("Flight Software & Avionics", "flight-software-avionics", "Electronics & Software", 5),
        ("Propulsion & Thrusters", "propulsion-thrusters", "Propulsion", 6),
        ("Space Careers & Academia", "space-careers-academia", "General", 7),
    ]
    for name, slug, cat, order in initial_domains:
        op.execute(
            sa.text(
                "INSERT INTO mentor_domains (id, name, slug, category, is_active, display_order, created_at) "
                f"VALUES (gen_random_uuid(), '{name}', '{slug}', '{cat}', true, {order}, now()) "
                "ON CONFLICT (slug) DO NOTHING"
            )
        )


def downgrade() -> None:
    op.drop_index("idx_mentor_booking_slot", table_name="mentor_bookings")
    op.drop_index("ix_mentor_bookings_cancel_token", table_name="mentor_bookings")
    op.drop_index("ix_mentor_bookings_gateway_token", table_name="mentor_bookings")
    op.drop_index("ix_mentor_bookings_mentor_id", table_name="mentor_bookings")
    op.drop_table("mentor_bookings")

    op.drop_index("ix_mentor_availabilities_mentor_id", table_name="mentor_availabilities")
    op.drop_table("mentor_availabilities")

    op.drop_table("mentor_profile_domains")

    op.drop_index("ix_mentor_profiles_user_id", table_name="mentor_profiles")
    op.drop_index("ix_mentor_profiles_slug", table_name="mentor_profiles")
    op.drop_table("mentor_profiles")

    op.drop_index("ix_mentor_domains_slug", table_name="mentor_domains")
    op.drop_table("mentor_domains")
