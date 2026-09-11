import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db.base import Base


class DesignComponentConfig(Base):
    """Program defaults and cohort overrides for the CubeSat component library.
    Allows disabling entire subsystems, hardware kits/tags, and individual components.

    - owner_type: 'program' (LmsProgram.id) or 'cohort' (Cohort.id)
    - owner_id: UUID of the owning LmsProgram or Cohort
    - disabled_subsystems: JSONB list of subsystem strings, e.g. ["Thermal", "ADCS"]
    - disabled_tags: JSONB list of tag strings, e.g. ["TinkerCAD", "SatKit"]
    - disabled_component_ids: JSONB list of string UUIDs for individual parts disabled
    """

    __tablename__ = "design_component_configs"
    __table_args__ = (
        UniqueConstraint("owner_type", "owner_id", name="uq_design_component_configs_owner"),
        Index("ix_design_component_configs_owner", "owner_type", "owner_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_type = Column(String(16), nullable=False)  # 'program' | 'cohort'
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    disabled_subsystems = Column(JSONB, nullable=False, default=list, server_default="[]")
    disabled_tags = Column(JSONB, nullable=False, default=list, server_default="[]")
    disabled_component_ids = Column(JSONB, nullable=False, default=list, server_default="[]")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
