"""student nicknames (Live Games Phase 2C, 8-1, 2026-08-12)

Adds `users.nickname` (unique, nullable — NULL for every non-student
account) and `users.nickname_rerolled_at`. Backfills every EXISTING
student account, not just new ones going forward — see
services/nicknames.py for the real (app-side) generator this mirrors;
kept self-contained here rather than imported, same posture as the
`delivery_roles` migration's own inlined seed data, so this migration
keeps working unchanged even if the app-side word pools grow later.

Revision ID: 851d4a6219af
Revises: e176025da286
Create Date: 2026-08-11 18:47:55.853435

"""
import random
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '851d4a6219af'
down_revision: Union[str, None] = 'e176025da286'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COSMIC_WORDS = [
    "Nebula", "Quasar", "Orbit", "Comet", "Solar", "Lunar", "Ion", "Vega",
    "Astro", "Pulsar", "Meteor", "Helios", "Titan", "Drift", "Zenith",
    "Nova", "Cosmo", "Stellar", "Lumen", "Photon", "Gravity", "Eclipse",
    "Aurora", "Corona", "Galactic", "Cryo", "Plasma", "Radiant", "Umbra",
    "Celestial", "Meridian", "Apogee", "Perigee", "Parallax", "Zero-G",
    "Vector", "Warp", "Cislunar", "Interstellar", "Polaris", "Equinox",
    "Solstice", "Magnetar", "Cosmic", "Astral", "Lightyear", "Voyager",
    "Ranger", "Pioneer", "Odyssey",
]

CREATURE_WORDS = [
    "Falcon", "Lynx", "Raven", "Magpie", "Otter", "Halcyon", "Puma",
    "Badger", "Kite", "Sable", "Wren", "Corvid", "Ibis", "Moth", "Heron",
    "Osprey", "Jackal", "Mantis", "Cobra", "Panther", "Coyote",
    "Kestrel", "Weasel", "Marten", "Bison", "Condor", "Gecko", "Hawk",
    "Ferret", "Vulture", "Jaguar", "Lemur", "Mongoose", "Ocelot", "Owl",
    "Peregrine", "Stoat", "Tern", "Viper", "Wolverine", "Bittern",
    "Caracal", "Dingo", "Egret", "Fennec", "Grouse", "Harrier", "Ibex",
    "Jackdaw",
]


def _candidate() -> str:
    number = random.randint(100, 999)
    return f"{random.choice(COSMIC_WORDS)}{random.choice(CREATURE_WORDS)}{number}"


def upgrade() -> None:
    op.add_column("users", sa.Column("nickname", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("nickname_rerolled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_users_nickname", "users", ["nickname"])

    conn = op.get_bind()
    student_ids = conn.execute(sa.text(
        "SELECT id FROM users WHERE 'student' = ANY(roles) AND nickname IS NULL"
    )).scalars().all()
    taken: set[str] = set(conn.execute(sa.text(
        "SELECT nickname FROM users WHERE nickname IS NOT NULL"
    )).scalars().all())
    for user_id in student_ids:
        candidate = _candidate()
        while candidate in taken:
            candidate = _candidate()
        taken.add(candidate)
        conn.execute(
            sa.text("UPDATE users SET nickname = :nickname WHERE id = :id"),
            {"nickname": candidate, "id": user_id},
        )


def downgrade() -> None:
    op.drop_constraint("uq_users_nickname", "users", type_="unique")
    op.drop_column("users", "nickname_rerolled_at")
    op.drop_column("users", "nickname")
