"""Auto-incrementing "N/YYYY" internship-letter reference number.

Operator spec (2026-08-20): admin overrides the number to Y at approval ->
the next auto-generated number in that same year is Y + 1; the counter
rolls over to 1 on the first approval of a new year. Backed by one row per
year in `internship_ref_counters`, row-locked so two concurrent approvals
never hand out the same number — an admin-only, low-frequency action, so a
locked counter is simpler and safe enough (no need for the Stripe-purchases-
style unique-index race protection).

Lazily seeded on first use per year from the highest ref_number already on
`intern_profiles` for that year — this is what lets the bulk-imported
historical rows (e.g. up to "85/2026") and the auto-counter coexist without
a separate one-off seeding script: the first real approval in 2026
continues from "86/2026" automatically, whenever it happens to run.
"""

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.internship import InternProfile, InternshipRefCounter

_REF_RE = re.compile(r"^(\d+)/(\d{4})$")


async def _max_existing_ref_for_year(db: AsyncSession, year: int) -> int:
    rows = (await db.execute(
        select(InternProfile.ref_number).where(InternProfile.ref_number.isnot(None))
    )).scalars().all()
    max_n = 0
    for raw in rows:
        m = _REF_RE.match(raw or "")
        if m and int(m.group(2)) == year:
            max_n = max(max_n, int(m.group(1)))
    return max_n


async def next_ref_number(db: AsyncSession, *, year: int | None = None, override: int | None = None) -> str:
    """Allocates the next internship-letter reference number for `year`
    (default: current calendar year). Must be called inside the same
    transaction that will be committed on approval — the row lock is only
    meaningful until that commit/rollback.

    `override`: admin typed a specific number at approval time. Returns
    exactly that value, formatted, and bumps the counter so the *next*
    auto-generated number in this year is override + 1."""
    year = year or date.today().year

    # Insert-if-absent, then lock — avoids a race between two concurrent
    # first-uses of a brand-new year both trying to INSERT the PK.
    await db.execute(
        pg_insert(InternshipRefCounter)
        .values(year=year, last_number=0)
        .on_conflict_do_nothing(index_elements=["year"])
    )
    counter = (await db.execute(
        select(InternshipRefCounter).where(InternshipRefCounter.year == year).with_for_update()
    )).scalar_one()

    if counter.last_number == 0:
        counter.last_number = await _max_existing_ref_for_year(db, year)

    if override is not None:
        counter.last_number = max(counter.last_number, override)
        return f"{override}/{year}"

    counter.last_number += 1
    return f"{counter.last_number}/{year}"
