from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from app.db.base import Base


class WebsiteConfig(Base):
    """Singleton row (id=1) backing the public marketing site's global config.

    Step 1 — SpacePoint Website Global Config & Live Counters: administrators
    edit these values from the portal (/operations/website) and the public
    site reads them via GET /public/website/config without a redeploy.
    """

    __tablename__ = "website_settings"

    id = Column(Integer, primary_key=True, default=1)
    students_count = Column(String(64), nullable=False, default="2,700+")
    workshops_count = Column(String(64), nullable=False, default="40+")
    partners_count = Column(String(64), nullable=False, default="25")
    satellites_flown_count = Column(String(64), nullable=False, default="50+")
    instructor_invite_code = Column(String(64), nullable=True, default="UOWD26")
    intern_invite_code = Column(String(64), nullable=True, default="UOWD26")
    contact_email = Column(String(255), nullable=False, default="info@spacepoint.ae")
    contact_phone = Column(String(64), nullable=False, default="+971 56 298 7005")
    contact_whatsapp = Column(String(64), nullable=True, default="+971 56 298 7005")
    office_address = Column(
        String(255),
        nullable=False,
        default="Sharjah Research, Technology and Innovation Park (SRTIP), Block B – Office B22-120, Sharjah, United Arab Emirates",
    )
    social_linkedin = Column(
        String(255),
        nullable=True,
        default="https://www.linkedin.com/company/spacepointae/posts/?feedView=all",
    )
    social_x = Column(
        String(255),
        nullable=True,
        default="https://www.tiktok.com/@spacepoint.ae",
    )
    social_instagram = Column(
        String(255),
        nullable=True,
        default="https://www.instagram.com/spacepoint.ae",
    )
    social_youtube = Column(String(255), nullable=True, default="")
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
