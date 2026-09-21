import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ProgramCertificateTemplate(Base):
    """Custom certificate layout and styling template configured per program.

    Allows programs to define custom certificate backgrounds, typography,
    text positioning (name and description), and signature block placement,
    overriding or augmenting the stock dark and light default templates.
    """

    __tablename__ = "program_certificate_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    program_id = Column(
        UUID(as_uuid=True),
        ForeignKey("programs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    background_type = Column(String(24), nullable=False, default="custom")  # "custom" | "dark" | "light"
    background_file_path = Column(String(512), nullable=True)
    background_file_url = Column(String(512), nullable=True)

    # Recipient Name typography and position (pt in A4 landscape: 841.89 x 595.27)
    name_font_size = Column(Integer, nullable=False, default=34)
    name_y = Column(Numeric(6, 2), nullable=False, default=298.0)
    name_color = Column(String(32), nullable=False, default="#9778be")

    # Body Description typography and position
    body_text = Column(Text, nullable=True)
    body_font_size = Column(Integer, nullable=False, default=20)
    body_y = Column(Numeric(6, 2), nullable=False, default=260.0)
    body_color = Column(String(32), nullable=False, default="#9778be")
    body_max_width = Column(Numeric(6, 2), nullable=False, default=600.0)
    body_alignment = Column(String(16), nullable=False, default="center")

    # Signature placement
    show_signature = Column(Boolean, nullable=False, default=False)
    signature_image_path = Column(String(512), nullable=True)
    signature_image_url = Column(String(512), nullable=True)
    signature_x = Column(Numeric(6, 2), nullable=True)  # if None, centered at (page_width - width) / 2
    signature_y = Column(Numeric(6, 2), nullable=False, default=90.0)
    signature_width = Column(Numeric(6, 2), nullable=False, default=140.0)
    signature_height = Column(Numeric(6, 2), nullable=False, default=50.0)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
