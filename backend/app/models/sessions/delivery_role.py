import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class DeliveryRole(Base):
    """What someone is doing on a session — Lead Facilitator, Facilitator,
    Assistant Facilitator, or whatever ops adds next (I5-3).

    **Roles are data, not an enum**, on the operator's decision. The concrete
    problem it solves: staffing used `lead|co` while payment letters used a
    three-value Postgres enum ("Lead Facilitator" / "Facilitator" /
    "Assistant Facilitator"), and the bridge between them had no honest
    mapping — `co` is not the same claim as "Facilitator", and picking one
    silently would have put a wrong word on a signed document. One vocabulary
    removes the problem instead of papering over it.

    `sort_order` is seniority, lowest first. It is not decoration: anything
    that needs "the lead" reads the lowest sort_order among a session's
    assigned roles rather than matching a name, so renaming a role or adding
    one above it does not break the notion of who is in charge.

    Deactivating rather than deleting is the norm — a role that has ever been
    assigned is referenced by history.
    """

    __tablename__ = "delivery_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(64), nullable=False, unique=True)
    sort_order = Column(Integer, nullable=False, default=1)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
