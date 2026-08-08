from sqlalchemy import Boolean, Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.db.base import Base


class ApplicantProfile(Base):
    __tablename__ = "applicant_profiles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    university = Column(String(255), nullable=True)
    highest_degree = Column(String(100), nullable=True)
    highest_degree_other = Column(String(255), nullable=True)
    # Structured (2026-08-08) — replaced the old free-text city_of_residence/
    # deliver_cities string columns; see the "cities" migration for the
    # case-insensitive backfill that preserved existing applicants' data.
    city_of_residence_id = Column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="SET NULL"), nullable=True)
    deliver_city_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    background_areas = Column(ARRAY(String), nullable=True)
    background_other = Column(String(255), nullable=True)
    has_own_transportation = Column(Boolean, nullable=False, default=False)
    country = Column(String(100), nullable=False, default="United Arab Emirates")
    cv_path = Column(Text, nullable=True)  # storage path in the "cvs" bucket
    # NOTE: the referring ambassador is tracked on users.invited_by_id (single source
    # of truth) — there is intentionally no duplicate referred_by_ambassador_id here.

    # Set when this applicant was routed into the instructor pipeline from another
    # role's application (e.g. an intern applicant sent to onboarding) instead of
    # signing up organically. On final approval, review_applicant() unions this role
    # into the instructor role instead of overwriting — see routers/instructors/admin.py.
    also_grant_role = Column(String(50), nullable=True)
