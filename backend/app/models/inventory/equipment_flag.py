import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class EquipmentReturnFlag(Base):
    """"I'll bring this back later" for a piece of session equipment.

    Equipment has no counterpart to `session_kits.return_status` — what
    happened lives entirely in the movement ledger (issue vs. return,
    netted). A flag is needed for the one thing the ledger can't say on its
    own: "nothing has moved yet, but the instructor already decided" — so
    that survives a page reload instead of only being remembered by the
    browser. Cleared the moment the item is actually returned, which is what
    makes "returned" and "later" mutually exclusive without a status column.
    """

    __tablename__ = "equipment_return_flags"
    __table_args__ = (
        UniqueConstraint("session_id", "item_id", "user_id", name="uq_equipment_return_flag"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id = Column(
        UUID(as_uuid=True), ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
