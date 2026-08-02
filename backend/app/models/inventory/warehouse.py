import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class Warehouse(Base):
    """A physical warehouse, depot, or storage room that belongs to a parent Location.

    Every kit and stock level resides at a specific warehouse. Multiple warehouses
    can exist per Location (e.g. Dubai Main Warehouse, Dubai Co-working Depot).
    """

    __tablename__ = "warehouses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    location_id = Column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name = Column(String(128), nullable=False)
    code = Column(String(32), nullable=True)  # e.g., WH-DXB-01
    is_active = Column(Boolean, nullable=False, default=True)
    address = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    location = relationship("Location", foreign_keys=[location_id])
