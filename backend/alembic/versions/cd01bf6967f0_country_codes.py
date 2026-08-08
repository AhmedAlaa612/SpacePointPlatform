"""Country free-text → ISO code (2026-08-08) — `users.country`,
`applicant_profiles.country`, `applications.country` moved onto the same
ISO-3166-1 alpha-2 convention `Location.country`/`City.country` already use,
closing the two-storage-convention split `CountrySelect.tsx` used to
accommodate on purpose.

No column type change — these stay `VARCHAR`, just holding 2-char codes
going forward instead of display names. Resolution reuses
`app.services.countries.resolve_country_code` (case/whitespace-insensitive
against the same list `frontend/src/lib/countries.ts` renders) so the
migration's matching logic and the reusable resolver can never drift apart.

Verified against a restored production snapshot before writing this:
`users.country` had `"United Arab Emirates"` (21), `"UAE"` (1, already
normalized to the full name by a pre-deploy hand-run `UPDATE`),
`"Kuwait"` (1), `"Nigeria"` (1) — all resolve cleanly. Same shape for
`applicant_profiles.country`/`applications.country` (UAE-only). A value
that doesn't resolve (typo, garbage, a name this list doesn't recognize) is
left untouched rather than nulled or guessed — it just won't pre-select in
the country dropdown until someone re-picks it, the exact same "unmatched
stays visible, never destroyed" rule the `locations` → `city_id` backfill
follows.

Revision ID: cd01bf6967f0
Revises: f0a1b2c3d4e5
Create Date: 2026-08-08
"""

import sqlalchemy as sa
from alembic import op

from app.services.countries import resolve_country_code

revision = "cd01bf6967f0"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None

_TABLES = ["users", "applicant_profiles", "applications"]


def upgrade() -> None:
    connection = op.get_bind()
    for table in _TABLES:
        distinct_values = connection.execute(
            sa.text(f"SELECT DISTINCT country FROM {table} WHERE country IS NOT NULL AND trim(country) <> ''")
        ).scalars().all()
        for original in distinct_values:
            code = resolve_country_code(original)
            if code is None:
                continue
            connection.execute(
                sa.text(f"UPDATE {table} SET country = :code WHERE country = :original"),
                {"code": code, "original": original},
            )


def downgrade() -> None:
    # Best-effort data repair, same as the locations->city_id backfill —
    # reversing would mean guessing a display name back from a code, which
    # is exactly the kind of lossy round-trip this migration exists to
    # avoid. Codes remain valid strings either way; nothing to undo.
    pass
