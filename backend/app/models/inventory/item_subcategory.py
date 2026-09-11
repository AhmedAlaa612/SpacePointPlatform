import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class ItemSubcategory(Base):
    """A sub-grouping under an ItemCategory (e.g. 'microcontroller' under 'board').

    `items.subcategory` stores this row's `name` as a plain string, matching
    `items.category`'s design. Renaming relabels every item in the parent category
    using the old name in the same transaction. Deleting is refused while any item
    in the category still uses it.
    """

    __tablename__ = "item_subcategories"
    __table_args__ = (
        UniqueConstraint("category_id", "name", name="uq_item_subcategories_category_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = Column(
        UUID(as_uuid=True),
        ForeignKey("item_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(64), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    category = relationship("ItemCategory", back_populates="subcategories")
