import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.db.base import Base


class SessionOpening(Base):
    """One role a session needs filling, with how many and for how much (I5-4).

    An offer is not one number on a session — it is per role: *this session
    needs 1 Lead Facilitator at 2000 and 2 Assistants at 400.* That is what
    ops actually types when opening a call, and it is what an instructor
    needs to see on the invite.

    **The consequence to go in with eyes open:** `sessions.staffing_status` is
    one flag per session, so an open call was all-or-nothing. With openings a
    session can be *half* staffed — Lead filled, Assistants still open. That
    is more correct and it is what the CEO described, but it is the biggest
    change in this batch and it touches the marketplace instructors already
    use. `staffing_status` is kept and still maintained, so nothing that reads
    it breaks; it now means "every opening filled" rather than "somebody was
    assigned".

    Slots remaining is `slots` minus assignments, and the waitlist is interest
    beyond that. Both fall out — neither is stored.
    """

    __tablename__ = "session_openings"
    __table_args__ = (
        UniqueConstraint("session_id", "role_id", name="uq_session_opening_role"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id = Column(UUID(as_uuid=True), ForeignKey("delivery_roles.id", ondelete="RESTRICT"), nullable=False)
    slots = Column(Integer, nullable=False, default=1)
    # Ops types the offer when opening the call. Rates configured per program
    # can come later — that was explicitly deferred (operator, 2026-07-29).
    amount_aed = Column(Numeric(10, 2), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SessionAddon(Base):
    """Extra money attached to a session, on top of the role's offer — poster
    printing, a taxi, an extra hour (§G-addons).

    **Attached to the session, not to the opening** (operator, 2026-07-30).
    Add-ons arise at five different moments and the opening only exists at one
    of them:

    | When | `source` | Starts as |
    |---|---|---|
    | Ops opens the call | `offer` | `agreed` |
    | Instructor's interest response | `interest` | `proposed` |
    | On a specific invite | `invite` | `agreed` |
    | Post-session survey | `survey` | `proposed` |
    | Payment prep | `payment` | `agreed` |

    Hanging these off `session_openings` would have worked for the first row
    of that table and nothing else — by the fourth the opening is closed.

    **`proposed` vs `agreed` is the whole approval mechanism.** Anything an
    instructor raises is a request until ops agrees it; anything ops offers is
    already agreed. One column does the work of an approval feature, and "what
    did they ask for that we never answered" becomes a query rather than a gap.

    `user_id` NULL means the add-on belongs to the *role* — part of the offer
    for whoever takes it — which is how the per-opening idea survives without
    an `opening_id`.

    Building a payment letter copies `agreed` rows into `PaymentAddon`, which
    stays exactly as it is: the frozen document snapshot. Same live-vs-frozen
    split as `payment_sessions.role`. Documents freeze; live records don't.
    """

    __tablename__ = "session_addons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    # NULL = attached to the role, unclaimed. Set = this person's.
    # SET NULL, never CASCADE — a departed instructor must not erase the
    # record of money that was agreed (same rule as custody, D1).
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    # Only meaningful while user_id is NULL.
    role_id = Column(UUID(as_uuid=True), ForeignKey("delivery_roles.id", ondelete="SET NULL"), nullable=True)

    description = Column(String(255), nullable=False)
    amount_aed = Column(Numeric(10, 2), nullable=False, default=0)
    notes = Column(String(255), nullable=True)

    # offer|interest|invite|survey|payment — where it came from.
    source = Column(String(16), nullable=False, default="offer")
    # proposed|agreed|declined
    status = Column(String(16), nullable=False, default="proposed")

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
