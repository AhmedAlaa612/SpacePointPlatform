"""The standardized video service's own playback surface — one route for
every `hls_encrypted` video regardless of who owns it, replacing the
LMS-only `routers/lms/video.py` (kept, for now, only for its upload
endpoint; see that file's own note).

The mechanics here (decode token, load the `Video` row, fetch from
whichever backend it lives on, rewrite the playlist) are 100% owner-type-
agnostic — they always were, they just used to be duplicated inside the LMS
router because LMS was the only caller. The only thing that ever varies by
feature is the ACCESS CHECK: "enrolled in this course" vs "is an
instructor" vs "assigned this checklist item". `_ACCESS_CHECKS` is that one
point of variation — each entry is a small, self-contained predicate that
raises on denial, exactly the shape `_assert_enrolled` already had. Nothing
here imports another feature's access logic; each check only reads what it
needs off `(db, video, user)`.

Keyed by `video_id` throughout (the Video's own primary key), not by
whatever id the owning row happens to use — the one thing every owner_type
has in common."""

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user, require_instructor, require_lms_content
from app.core.security import create_video_token, decode_video_token
from app.core.timing import phase
from app.db.session import get_db
from app.models.lms import CourseModule, Enrollment, ModuleItem
from app.models.lms.program import LmsProgramAssignment, LmsProgramItemProgress
from app.models.user import User
from app.models.videos import Video
from app.services import hls_cache, storage
from app.services.lms.enrollment import enrollment_is_active
from app.services.video_service import HLS_BUCKET, _hls_backend

router = APIRouter(prefix="/videos", tags=["video"])

# Must cover the longest lecture plus a mid-lesson pause — see create_video_token.
# Passed explicitly rather than relying on its default: this constant is what
# the client is *told* the expiry is, so if the two drift the player's
# refresh timing silently disagrees with reality.
_VIDEO_TOKEN_MINUTES = 4 * 60
# `%03d` in video_service.py is a *minimum* width — segment 1000 writes as
# "segment_1000.ts". A fixed \d{3} 404s on anything past segment 999
# (66m36s at the old 4s segment length; ~4h10m at the current 10s), a hard
# mid-playback stop indistinguishable from a network failure.
_SEGMENT_NAME_RE = re.compile(r"^segment_\d{3,}\.ts$")
_KEY_URI_RE = re.compile(r'URI="[^"]*"')


async def _check_module_item(db: AsyncSession, video: Video, user: User) -> None:
    """`owner_type="module_item"` — enrolled in the owning course. Same
    flat-404-for-both rule `_assert_enrolled` always used: "not enrolled"
    and "unknown course" must read identically, so neither leaks whether a
    course exists at all.

    One joined query instead of three sequential round trips (was: get
    ModuleItem, get CourseModule, select Enrollment) — found under a
    competition-day load test (400 concurrent `/token` calls) that this
    endpoint's real bottleneck wasn't Postgres (confirmed idle, waiting on
    the client) but per-request Python/ORM overhead stacking up across three
    round trips inside uvicorn's single-threaded event loop. A missing
    ModuleItem/CourseModule or a non-matching/inactive Enrollment all land
    on the same empty-result 404 as before, so the flat-404 behavior is
    unchanged — only the round-trip count is."""
    exists = await db.scalar(
        select(Enrollment.id)
        .join(CourseModule, CourseModule.course_id == Enrollment.course_id)
        .join(ModuleItem, ModuleItem.module_id == CourseModule.id)
        .where(
            ModuleItem.id == video.owner_id,
            Enrollment.user_id == user.id,
            *enrollment_is_active(),
        )
        .limit(1)
    )
    if exists is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")


async def _check_program_item_guideline(db: AsyncSession, video: Video, user: User) -> None:
    """`owner_type="program_item_guideline"` — the student has a progress row
    for this checklist item on some assignment of their own. Deliberately
    not scoped to one particular assignment_id: the same checklist item (and
    so the same guideline video) can be shared across many students'
    assignments, and all any of them need to prove is "this item is on a
    checklist actually assigned to me", not which specific assignment.

    Falls back to "can author checklist items at all" (same role gate
    `upload_program_item_guideline_video` itself uses) for whoever isn't a
    student with a progress row — the authoring UI's own "Preview" button on
    an uploaded guideline video hits this exact endpoint, and its facilitator/
    operations caller was never assigned the checklist item as a student."""
    exists = await db.scalar(
        select(LmsProgramItemProgress.id)
        .join(LmsProgramAssignment, LmsProgramItemProgress.assignment_id == LmsProgramAssignment.id)
        .where(LmsProgramItemProgress.item_id == video.owner_id, LmsProgramAssignment.user_id == user.id)
        .limit(1)
    )
    if exists is not None:
        return
    try:
        await require_lms_content(current_user=user)
    except HTTPException:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")


async def _check_any_instructor(db: AsyncSession, video: Video, user: User) -> None:
    """`owner_type="library_resource"` and `"training_video"` — both are
    "any authenticated instructor", no ownership/enrollment concept at all.
    Calling `require_instructor` directly (outside of FastAPI's DI, with the
    already-resolved `user` passed by keyword) reuses its exact rule —
    including "admin always passes" — instead of restating it here."""
    await require_instructor(current_user=user)


# owner_type -> async (db, video, user) -> None, raises on denial. Adding a
# new owner_type (a future Guides feature, say) means adding one entry here,
# never touching the routes below.
_ACCESS_CHECKS = {
    "module_item": _check_module_item,
    "program_item_guideline": _check_program_item_guideline,
    "library_resource": _check_any_instructor,
    "training_video": _check_any_instructor,
}


async def _load_and_check(db: AsyncSession, video_id: uuid.UUID, user: User) -> Video:
    video = await db.get(Video, video_id)
    if video is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")
    check = _ACCESS_CHECKS.get(video.owner_type)
    if check is None:
        # An owner_type with no registered check is a bug in this module,
        # not a client error — refuse rather than silently allow.
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")
    await check(db, video, user)
    return video


@router.get("/{video_id}/token")
async def issue_video_token(
    video_id: uuid.UUID, db: AsyncSession = Depends(get_db), current: User = Depends(get_current_active_user),
):
    with phase("db"):
        video = await _load_and_check(db, video_id, current)
        if video.upload_mode != "hls_encrypted":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="This video is not HLS-encrypted")
        if video.status != "ready":
            raise HTTPException(status.HTTP_409_CONFLICT, detail="Video is not ready yet")
    token = create_video_token(current.id, video.id, expires_delta=timedelta(minutes=_VIDEO_TOKEN_MINUTES))
    return {"token": token, "expires_in_seconds": _VIDEO_TOKEN_MINUTES * 60}


@dataclass(frozen=True, slots=True)
class _PlaybackRef:
    """Everything the playlist/segment/key routes need once the database is
    done with them.

    A frozen snapshot rather than the ORM `Video` itself, because those routes
    now release the DB session *before* touching R2 (see `_video_from_token`).
    A detached instance would still be reachable there, and any attribute that
    happened not to be loaded would try to lazy-load off a connection nobody
    holds any more. Copying the four fields out makes that impossible instead
    of merely unlikely."""

    video_id: uuid.UUID
    playlist_path: str
    key_path: str
    backend: str | None

    @property
    def prefix(self) -> str:
        """The storage directory this video's segments/key actually live under.

        Always derived from playlist_path, NEVER assumed to equal video.id —
        the unify_video_service migration backfilled every pre-existing video
        with a freshly generated id while copying playlist_path verbatim, so
        for every video that predates it the prefix is the old owner-row id,
        not this row's own. A re-encode (see
        video_service.run_encrypted_transcode) keeps reusing that same
        established prefix on purpose, so this must keep matching it exactly
        or it fetches objects that do not exist."""
        return self.playlist_path.rsplit("/", 1)[0]


async def _video_from_token(db: AsyncSession, video_id: uuid.UUID, token: str) -> _PlaybackRef:
    """Playlist/segment/key all funnel through here — deliberately NOT
    through `_load_and_check`'s owner-type access check again. That check
    (the enrollment join, or the instructor/guideline checks) already ran
    once, at token-mint time (`issue_video_token`), and the token itself —
    signed with our own secret, bound to this exact user+video, short-lived —
    IS the proof it passed.

    Trade-off, stated plainly: revoking a student's enrollment mid-session no
    longer cuts off an already-started playback instantly, only once the
    token itself expires (`_VIDEO_TOKEN_MINUTES`, 4 hours) — the same
    trade-off most short-lived signed-URL video systems make. Still checked
    here on every call: the token's signature and expiry (forgery/tampering),
    that it was minted for this exact video id (can't be replayed against a
    different one), that the user row still exists (catches a deleted
    account), and that the video is still `ready`.

    **Returns a detached snapshot, and closes the session before it does.**
    That closing line is the load-bearing part. `get_db` keeps the session —
    and therefore its pooled connection — checked out for the whole request,
    so before this change a `/playlist` call held one of the 15 connections
    this worker has (`pool_size=10 + max_overflow=5`) for the entire R2
    download and every presign after it. The connection sat idle in
    `ClientRead` the whole time, which is exactly what `pg_stat_activity`
    showed during the load tests and exactly why it was misread as "Postgres
    is not the bottleneck": Postgres was not, but its *checkout* was, because
    hold time was set by R2 latency rather than by query count. That is also
    why #51 and #52 moved nothing — removing queries does not shorten a hold
    whose length is decided by the network call that follows them."""
    try:
        user_id, token_video_id = decode_video_token(token)
    except JWTError:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid or expired token")
    # A well-formed, unexpired token minted for a *different* video — distinct
    # from "no such video" (404) so a valid token never leaks which of the
    # two is actually true.
    if uuid.UUID(token_video_id) != video_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Token does not match this video")

    # One round trip for both facts (video row + "does that user still
    # exist"), rather than two sequential `db.get`s. Same reasoning as #51,
    # but now the round trips it saves are ones the connection is held open
    # across, which is what actually costs.
    with phase("db"):
        row = (
            await db.execute(
                select(Video, select(User.id).where(User.id == uuid.UUID(user_id)).exists())
                .where(Video.id == video_id)
            )
        ).first()

        if row is None:
            # No video row, so the combined query returned nothing and cannot
            # say whether the user exists. Only reachable on a 403/404 path, so
            # the extra round trip costs nothing that matters — and it keeps
            # "deleted user" reporting 403 ahead of the video's 404, exactly as
            # before.
            user_exists = await db.scalar(select(User.id).where(User.id == uuid.UUID(user_id)))
            if user_exists is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid or expired token")
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")

        video, user_exists = row
        if not user_exists:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invalid or expired token")
        if video.status != "ready":
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Video not found")

        ref = _PlaybackRef(
            video_id=video.id,
            playlist_path=video.playlist_path,
            key_path=video.key_path,
            backend=_hls_backend(video),
        )
        # Hand the connection back NOW, before any R2 call. `get_db`'s
        # `async with` closes again on the way out, which is a no-op.
        await db.close()
    return ref


async def _rewrite_playlist(raw: bytes, ref: _PlaybackRef, token: str, *, expires_in: int) -> bytes:
    """Stored playlists carry plain relative filenames (token-agnostic — one
    file serves every viewer). Rewritten per-request so every segment/key
    reference is scoped to *this* request.

    Two shapes, chosen by where THIS video's HLS bytes actually live
    (per-row, not a global setting — see video.storage_backend):

    - Object store ("r2"): each segment line becomes an absolute presigned
      URL straight to the store, so segments never touch this API at all.
      Presigning is local HMAC: no network call, no billed operation.
    - Local/Supabase: relative `segment/{name}?token=` paths, resolved by
      this same router.

    The `#EXT-X-KEY` line stays relative and token-gated in BOTH shapes. The
    AES key never moves to the object store: segments sitting there are
    already AES-128 encrypted, so a leaked or expired segment URL yields
    ciphertext, and the key remains behind the same access check as before.

    Every segment line is signed in ONE batch (storage.get_signed_urls).
    Signing is microseconds of local HMAC, but it used to run through its own
    `await ... to_thread` per line: one worker-thread-limiter acquisition and
    one full lap of the event loop each, paid sequentially, once per segment.
    At 400 concurrent starts those laps are not free, and a half-hour lecture
    at 10s segments has ~180 of them — a per-request cost that scales with
    video length and so was invisible in a load test run against a 50-second
    clip."""
    presign = ref.backend == "r2"

    lines = raw.decode("utf-8").splitlines()
    # Index every segment line first so the whole playlist can be signed in
    # one go, then splice the URLs back into their original positions.
    segment_idx = [i for i, line in enumerate(lines) if line and not line.startswith("#")]

    signed: list[str] = []
    if presign and segment_idx:
        with phase("presign"):
            signed = await storage.get_signed_urls(
                HLS_BUCKET,
                [f"{ref.prefix}/{lines[i]}" for i in segment_idx],
                expires_in,
                backend=ref.backend,
            )

    out = list(lines)
    for n, i in enumerate(segment_idx):
        out[i] = signed[n] if presign else f"segment/{lines[i]}?token={token}"
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-KEY"):
            out[i] = _KEY_URI_RE.sub(f'URI="key?token={token}"', line)
    return ("\n".join(out) + "\n").encode("utf-8")


@router.get("/{video_id}/playlist")
async def get_playlist(video_id: uuid.UUID, token: str = Query(...), db: AsyncSession = Depends(get_db)):
    ref = await _video_from_token(db, video_id, token)
    # Cached: the stored playlist is the same bytes for every viewer (it is
    # rewritten per-request below, after the download), so 400 students
    # starting one video does not need 400 identical R2 round trips.
    raw = await hls_cache.download_cached(HLS_BUCKET, ref.playlist_path, backend=ref.backend)
    # Presigned segment URLs expire alongside the token that fetched this
    # playlist, so there is one failure mode rather than two interleaved
    # ones — the player's existing one-retry-on-network-error path re-issues
    # the token AND refetches the playlist, minting fresh URLs.
    rewritten = await _rewrite_playlist(raw, ref, token, expires_in=_VIDEO_TOKEN_MINUTES * 60)
    return Response(content=rewritten, media_type="application/vnd.apple.mpegurl")


@router.get("/{video_id}/segment/{segment_name}")
async def get_segment(
    video_id: uuid.UUID, segment_name: str, token: str = Query(...), db: AsyncSession = Depends(get_db),
):
    if not _SEGMENT_NAME_RE.match(segment_name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Segment not found")
    ref = await _video_from_token(db, video_id, token)
    # Only reachable when this video's segments are NOT on an object store —
    # an "r2" row's playlist already points hls.js straight at R2, so this
    # route never sees a request for one of those. Deliberately uncached:
    # segments are megabytes each and, unlike the playlist and key, a single
    # student streams a different one every few seconds.
    with phase("r2_download"):
        data = await storage.download_file(
            HLS_BUCKET, f"{ref.prefix}/{segment_name}", backend=ref.backend,
        )
    return Response(content=data, media_type="video/mp2t")


@router.get("/{video_id}/key")
async def get_key(video_id: uuid.UUID, token: str = Query(...), db: AsyncSession = Depends(get_db)):
    ref = await _video_from_token(db, video_id, token)
    # Cached for the same reason as the playlist: 16 bytes of AES material for
    # the video, identical for every viewer. The per-request access check that
    # decides whether to hand it over is upstream of this and unaffected.
    data = await hls_cache.download_cached(HLS_BUCKET, ref.key_path, backend=ref.backend)
    return Response(content=data, media_type="application/octet-stream")
