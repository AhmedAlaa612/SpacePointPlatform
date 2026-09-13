"""Shared config for the Phase 1 "watch and summarize" videos (2026-09) —
the applicant-facing lineup a facilitator edits from Application Content >
Video Links (`routers/instructors/facilitator.py`).

Previously duplicated as three separate hardcoded literal lists — the
signup handler (`routers/auth.py`), the facilitator admin endpoints
(`routers/instructors/facilitator.py`), and the applicant endpoints
(`routers/instructors/applicant.py`) each carried their own copy of the
same 3 URLs. Signup never actually read the facilitator's saved settings
at all, so editing a URL on the admin page silently had no effect on new
applicants despite the page's own copy claiming otherwise ("takes effect
for new applicants immediately"). This module is now the one place all
three read from.

Count and per-slot url/title live in the generic `portal_settings`
key/value table (`app_video_count`, `app_video_{n}_url`,
`app_video_{n}_title`) — no schema change needed since `video_no` on
`VideoSubmission` was never actually constrained to exactly 3 at the
database level, only by these call sites.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.payment import PortalSetting

# The 3 videos this feature originally shipped with — the fallback for
# slots 1-3 only, and only while a facilitator has never touched the
# settings for that slot (a fresh install, or before this page was ever
# opened). A slot beyond the original 3 that's never been configured has
# no baked-in default; it starts blank until a facilitator fills it in.
DEFAULT_VIDEO_URLS = [
    "https://youtu.be/6KcV1C1Ui5s",
    "https://youtu.be/qr1AvisQcV8",
    "https://youtu.be/5voQfQOTem8",
]
DEFAULT_VIDEO_TITLES = ["Video 1", "Video 2", "Video 3"]
DEFAULT_VIDEO_COUNT = len(DEFAULT_VIDEO_URLS)


async def get_configured_videos(db: AsyncSession) -> list[dict]:
    """The facilitator's current Phase 1 video lineup, in order:
    `[{"video_no": int, "url": str, "title": str}, ...]`.

    Single source of truth for three different call sites: what a
    brand-new signup gets seeded with (`routers/auth.py` — this is the
    fix, it used to carry its own frozen copy of `DEFAULT_VIDEO_URLS`
    instead of reading live settings), the applicant's first-visit list
    (`routers/instructors/applicant.py`), and the facilitator admin GET
    (`routers/instructors/facilitator.py`).
    """
    rows = (await db.execute(
        select(PortalSetting).where(PortalSetting.key.like("app_video_%"))
    )).scalars().all()
    values = {r.key: r.value for r in rows}
    count = int(values.get("app_video_count") or DEFAULT_VIDEO_COUNT)
    return [
        {
            "video_no": n,
            "url": values.get(f"app_video_{n}_url") or (DEFAULT_VIDEO_URLS[n - 1] if n <= DEFAULT_VIDEO_COUNT else ""),
            "title": values.get(f"app_video_{n}_title") or (DEFAULT_VIDEO_TITLES[n - 1] if n <= DEFAULT_VIDEO_COUNT else f"Video {n}"),
        }
        for n in range(1, count + 1)
    ]


async def set_configured_videos(db: AsyncSession, videos: list[dict]) -> None:
    """Replace the facilitator's video lineup with `videos` (already
    validated + renumbered 1..N by the caller). Upserts each slot's
    settings, deletes any leftover slots beyond the new count (so a later
    increase doesn't resurrect a stale title/url from a slot that was
    removed), and writes the new `app_video_count`. Caller commits.
    """
    new_count = len(videos)
    existing = {
        r.key: r
        for r in (await db.execute(
            select(PortalSetting).where(PortalSetting.key.like("app_video_%"))
        )).scalars().all()
    }
    old_count = int(existing["app_video_count"].value) if "app_video_count" in existing else DEFAULT_VIDEO_COUNT

    def _upsert(key: str, value: str) -> None:
        row = existing.get(key)
        if row:
            row.value = value
        else:
            db.add(PortalSetting(key=key, value=value))

    for v in videos:
        n = v["video_no"]
        _upsert(f"app_video_{n}_url", v["url"])
        _upsert(f"app_video_{n}_title", v["title"])

    for n in range(new_count + 1, max(old_count, new_count) + 1):
        for key in (f"app_video_{n}_url", f"app_video_{n}_title"):
            row = existing.get(key)
            if row:
                await db.delete(row)

    _upsert("app_video_count", str(new_count))
