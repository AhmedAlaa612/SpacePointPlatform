import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, text
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
    invited_by_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    must_change_password = Column(Boolean, nullable=False, default=False)
    recruit_points_awarded = Column(Boolean, nullable=False, default=False)
    phone = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def role_values(self) -> list[str]:
        """Roles as plain strings, regardless of how the driver hydrates the array."""
        return [r.value if isinstance(r, UserRole) else str(r) for r in (self.roles or [])]
