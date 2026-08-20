import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class InternProfile(Base):
    """1:1 intern record — mirrors instructor_profiles' shape. Populated either
    by the bulk-import script (historical rows: ref_number/university_id/
    department/start_date only, no letter — see scripts/bulk_import_interns.py)
    or by approving a `RoleRequest` targeting "intern" (adds duration/hours/
    work_city/supervisor and generates the internship letter)."""

    __tablename__ = "intern_profiles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    # "N/YYYY", e.g. "83/2026" — see services/internship/ref_number.py for the
    # per-year auto-increment. Not DB-unique: historical sheet rows can carry
    # malformed values (a handful of the earliest imported rows have a date
    # where the ref number should be) that must still land somewhere rather
    # than fail the import.
    ref_number = Column(String(50), nullable=True, index=True)
    university_id_number = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)  # free text — no controlled list on the source sheet
    start_date = Column(Date, nullable=True)  # first day of work
    duration_weeks = Column(Integer, nullable=True)  # null for historical bulk-imported rows
    hours_per_week = Column(Integer, nullable=True)  # null for historical bulk-imported rows
    work_city_id = Column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="SET NULL"), nullable=True)
    supervisor_name = Column(String(255), nullable=True)
    supervisor_email = Column(String(255), nullable=True)
    supervisor_phone = Column(String(50), nullable=True)
    # Fixed bucket "internship-letters" (not stored per-row — same convention
    # as InstructorProfile.contract_path's fixed "contracts" bucket).
    letter_path = Column(String, nullable=True)
    signed_letter_path = Column(String, nullable=True)
    letter_signature_data = Column(Text, nullable=True)
    letter_signed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RoleRequest(Base):
    """An already-authenticated user requesting an ADDITIONAL role — generic
    on purpose (2026-08-20 operator ask: build this once, generally, even
    though only instructor->intern is wired up today). NOT for brand-new
    signups (that's `Application`, which creates the User itself).

    Gated by an allowlist (services/internship/allowed_role_requests.py) of
    which current roles may request which target role. Adding a new
    direction later (e.g. intern -> instructor) is one allowlist entry plus
    an approval side-effect handler — no schema change.

    `details`/`resolution` are JSONB because the fields a request needs are
    entirely target_role-specific — today, for target_role="intern":
    details: university_id_number, preferred_city_id, requested_start_date,
             requested_duration_weeks
    resolution (admin-set at approval, all overridable): final_city_id,
             final_duration_weeks, final_hours_per_week, supervisor_name,
             supervisor_email, supervisor_phone, ref_number, letter_date
    """

    __tablename__ = "role_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requester_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_role = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="pending")  # pending | approved | rejected
    details = Column(JSONB, nullable=False, default=dict)
    resolution = Column(JSONB, nullable=False, default=dict)
    admin_notes = Column(Text, nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class InternshipRefCounter(Base):
    """Backs the auto-incrementing internship-letter ref number ("N/YYYY").
    One row per calendar year, row-locked (SELECT ... FOR UPDATE) on approval
    — admin-only, low-frequency, so a locked counter is simpler and safe
    enough (no need for the Stripe-style unique-index race protection).
    Seeded from the bulk-imported sheet's historical ref numbers per year so
    the first real new approval continues after the highest imported number
    instead of colliding with it."""

    __tablename__ = "internship_ref_counters"

    year = Column(Integer, primary_key=True, autoincrement=False)
    last_number = Column(Integer, nullable=False, default=0)
