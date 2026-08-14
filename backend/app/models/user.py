import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, UUID

from app.db.base import Base
from app.models.enums import UserRole


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    # Multi-role: a user can hold several roles at once. Admin checks look for
    # 'admin' in this array. The active role is client-side only (localStorage).
    roles = Column(
        ARRAY(ENUM(UserRole, name="user_role", create_type=False)),
        nullable=False,
        server_default=text("'{}'"),
    )

    status = Column(String(50), nullable=False, default="active")
    invite_code = Column(String(100), unique=True, nullable=True)  # ambassador's sharable code
    # The exact code THIS person typed at signup (admin-issued invitation_codes.code
    # or an ambassador's invite_code) — a distinct concept from invite_code above,
    # which is only ever set for ambassadors as their OWN sharable code. Mirrors the
    # legacy instructors-portal's users.invitation_code_used column 1:1.
    invitation_code_used = Column(String(100), nullable=True)
    invited_by_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    must_change_password = Column(Boolean, nullable=False, default=False)
    recruit_points_awarded = Column(Boolean, nullable=False, default=False)
    phone = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    # Structured (2026-08-08) — independent of the Contact spine's own
    # free-text city (too broad a field to restructure just for this),
    # same precedent as `country` above already being its own copy on User.
    city_id = Column(UUID(as_uuid=True), ForeignKey("cities.id", ondelete="SET NULL"), nullable=True, index=True)
    # Free-text fallback (2026-08-08) — the city pickers offer an "Other"
    # option for countries with no SpacePoint city; the typed value lands
    # here so form-prefill and admin review can show it. Mutually exclusive
    # with city_id in practice (Other only renders when no cities exist).
    city_other = Column(String(100), nullable=True)
    photo_url = Column(String, nullable=True)   # stored ready-to-use URL (hot read path); photo_path is the durable source of truth (A2)
    photo_path = Column(String, nullable=True)  # path inside the "profile_pictures" bucket
    linkedin_url = Column(String, nullable=True)
    # Shared identity number for ID cards — one per person, reused across every
    # role's card ("SP-{card_number:04d}-UAE"). Allocated on first-ever card
    # generation, never per-role. See services/documents/id_card.ensure_card_id.
    card_number = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # Per-account login lockout (B6, 2026-08-10). The existing rate_limit.py
    # brake is deliberately generous (1000/min/IP — a whole school shares one
    # IP) and useless against password guessing; this is the actual defence.
    # failed_login_count resets to 0 on a successful login; locked_until is
    # set once the count crosses the threshold and read before the password
    # is even checked, so a locked account can't be probed during its window.
    failed_login_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    locked_until = Column(DateTime(timezone=True), nullable=True)

    # Every user is also a spine contact (V2 R2-6) — lets staff (instructors,
    # ambassadors, etc.) show up in Contacts/merge-review flows the same way
    # public registrants do. Backfilled by scripts/backfill_user_contacts.py;
    # repointed on merge via identity.MERGE_FK_REGISTRY.
    # index=True (B4, 2026-08-10): every LMS lookup by contact_id was a
    # sequential scan. Standalone — not unique yet, contact_id can hold
    # duplicates until Phase 2 Stage 1's D1 migration reconciles them and
    # adds a UNIQUE constraint, which will make this index redundant
    # (Postgres backs a UNIQUE constraint with its own index) and it should
    # be dropped then.
    contact_id = Column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL", name="fk_users_contact_id"),
        nullable=True, index=True,
    )

    # Live Games (Phase 2C, 8-1). Students-only public identity: auto-
    # generated at account creation (services/nicknames.py), never a real
    # name — the platform's leaderboards and live games show this, never
    # full_name. NULL for every non-student account. Unique so two students
    # are never confusable on a shared leaderboard.
    nickname = Column(String(64), unique=True, nullable=True)
    nickname_rerolled_at = Column(DateTime(timezone=True), nullable=True)
    # The student's default game avatar (a key from
    # `services/games/avatars.py::AVATAR_PRESETS`). Avatars used to exist only
    # per game participation, which meant there was nothing for an admin —
    # or the student themselves outside a lobby — to actually set. A run still
    # carries its own snapshot; this is what it defaults from.
    avatar = Column(String(64), nullable=True)

    @property
    def role_values(self) -> list[str]:
        """Roles as plain strings, regardless of how the driver hydrates the array."""
        return [r.value if isinstance(r, UserRole) else str(r) for r in (self.roles or [])]
