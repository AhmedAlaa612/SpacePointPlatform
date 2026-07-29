import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class Movement(Base):
    """The one ledger. Everything that physically moves is a row here.

    This single table replaces four separate concepts in the legacy system —
    `receipts`, `package_requests`, `cubesat_session_logs` and implicit
    transfers — three of which had **zero rows after thirteen months**. They
    were separate features with separate screens; they are all the same event
    with different endpoints:

        refill request      warehouse -> warehouse, bulk
        kit issued          location  -> person, serialised, with due_back_on
        return              person    -> location
        warehouse transfer  location  -> location
        merch issued        location  -> person, bulk, due_back_on if returnable
        goods received      (no from) -> location

    **There is no status column.** An earlier draft had a five-state machine
    (requested/approved/in_transit/received/cancelled). It was cut because the
    legacy `package_requests` table has a row stuck in `on_way` since February
    — that is this exact failure mode, and five states means five ways to get
    stuck. Instead:

      created_at / created_by     it happened (or was asserted to)
      confirmed_at / confirmed_by the other party agreed

    Confirmation is **optional and never a gate** — a movement is real the
    moment it is created. Its absence is the signal: "ops marked it out but
    the instructor never confirmed collection" and "instructor says handed
    back but ops never received it" are the two states where things actually
    go wrong, and both fall out for free. A movement that didn't happen is
    deleted, not cancelled.

    Approval columns (`approved_by`/`approved_at`) are deliberately NOT here
    yet — nothing in Phase 1 or 2 approves anything, and shipping a column
    nothing reads is how schemas rot. They land with procurement.
    """

    __tablename__ = "movements"
    __table_args__ = (
        # Exactly one subject: a serialised kit, or a quantity of a bulk item.
        # Same idiom as certificates (user_id XOR contact_id) and
        # activity_assignments (program_id XOR cohort_id).
        CheckConstraint(
            "(kit_id IS NOT NULL) <> (item_id IS NOT NULL)",
            name="ck_movement_kit_xor_item",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    kit_id = Column(UUID(as_uuid=True), ForeignKey("kits.id", ondelete="CASCADE"), nullable=True, index=True)
    item_id = Column(UUID(as_uuid=True), ForeignKey("items.id", ondelete="RESTRICT"), nullable=True, index=True)
    # NULL for a kit (a kit is one thing); required for a bulk item.
    qty = Column(Integer, nullable=True)

    # Where it came from / went to. Either side may be a location or a person,
    # and either may be absent (goods arriving from a supplier have no `from`).
    from_location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=True)
    from_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    to_location_id = Column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="RESTRICT"), nullable=True)
    to_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Which session this movement was for, when it was for one. SET NULL so
    # deleting a session never destroys the custody record of a physical kit.
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # issue|return|transfer|refill|receive|writeoff|adjust|sold
    # Mostly derivable from the from/to shape, but stored so history reads
    # plainly without the reader reconstructing intent. `sold` is here from
    # the start because a kit leaving as a sale is permanent, and retrofitting
    # that into a ledger which assumes everything comes back is awkward.
    reason = Column(String(32), nullable=False)

    # Set when this is a loan. NULL means indefinite (a kit that lives with an
    # instructor, a T-shirt that was a gift). Overdue = due_back_on in the
    # past with no matching return.
    due_back_on = Column(Date, nullable=True, index=True)

    note = Column(Text, nullable=True)

    # RESTRICT: every movement has a real person behind it, and deleting that
    # user must not orphan the record. Same call as
    # attendance_records.recorded_by_user_id.
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
