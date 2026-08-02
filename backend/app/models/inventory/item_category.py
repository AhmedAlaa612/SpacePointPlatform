import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class ItemCategory(Base):
    """The catalogue's grouping vocabulary, editable in ops instead of
    hardcoded (same shape as `delivery_roles`, I5-3).

    `items.category` stores this row's `name` as a plain string, not a FK —
    the catalogue is a live classification with no signed document reading
    it, so there is nothing here that needs the live/frozen split
    `delivery_roles` has. Renaming relabels every item using the old name in
    the same transaction; deleting is refused while any item still uses it
    (checked at the router) — no soft-delete flag, because a category either
    has items or it doesn't, and that fact is a query, not a column.
    """

    __tablename__ = "item_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(32), nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
