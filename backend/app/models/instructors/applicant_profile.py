from sqlalchemy import Boolean, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.db.base import Base


class ApplicantProfile(Base):
    __tablename__ = "applicant_profiles"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    university = Column(String(255), nullable=True)
    highest_degree = Column(String(100), nullable=True)
    highest_degree_other = Column(String(255), nullable=True)
    city_of_residence = Column(String(100), nullable=True)
    deliver_cities = Column(ARRAY(String), nullable=True)
    background_areas = Column(ARRAY(String), nullable=True)
    background_other = Column(String(255), nullable=True)
    has_own_transportation = Column(Boolean, nullable=False, default=False)
    country = Column(String(100), nullable=False, default="United Arab Emirates")

    # Ambassador-referral hook (PLAN §4.3/§9.2): set when /apply/instructor's
    # invite code matched a users.invite_code rather than an admin invitation_code.
    referred_by_ambassador_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
