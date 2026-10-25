"""The instructor's day: check-in, the daily checklist, submission and ops
review (operations process doc §4-§12, scoped in 2026-08-24).

The shape, end to end:

    morning   instructor checks in, or declares an absence with a reason
    during    they work the resolved checklist, uploading proof where required
    evening   they submit the day
    after     ops approves it, or returns it with a comment to be redone

**That approval is the gate.** `status='approved'` and `att_status='present'`
is what makes a day a *paid* day (§18/§19) — nothing else in the system gets
to decide what counts as delivered, which is why `approve_day` is also where
cohort auto-completion is triggered from.

Checklist resolution is override-not-merge across program -> cohort -> session,
identical in rule and reasoning to `services/sessions/materials.py`. Proof
files go through the existing `services/sessions/reports.py`, never a second
upload path.

Authorisation follows `delivery.py`: `_get_deliverable_session` already means
"the assigned instructor, or ops/admin", and returns 404 rather than 403 for
someone unassigned so the endpoints don't leak which sessions exist.

Services raise `HTTPException` directly — house convention.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.checklist import (
    DeliveryChecklistItem,
    InstructorChecklistProgress,
    InstructorSessionDay,
    SessionOpsChecklistProgress,
)
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.session import Session, SessionInstructor
from app.models.sessions.session_report import SessionReport
from app.models.user import User
from app.services.sessions.delivery import _get_deliverable_session, complete_cohort
from app.services.sessions.reports import resolve_report_url

ATT_STATUSES = {"present", "absent"}
DAY_STATUSES = {"draft", "submitted", "changes_required", "approved"}


# ── checklist templates (ops) ───────────────────────────────────────────────

async def _items_at_level(
    db: AsyncSession, *,
    program_id: UUID | None = None, cohort_id: UUID | None = None, session_id: UUID | None = None,
    target_audience: str = "instructor",
) -> list[DeliveryChecklistItem]:
    """Every item set at exactly one level for a specific target_audience ('instructor' or 'internal')."""
    column = (
        DeliveryChecklistItem.program_id if program_id
        else DeliveryChecklistItem.cohort_id if cohort_id
        else DeliveryChecklistItem.session_id if session_id
        else None
    )
    value = program_id or cohort_id or session_id
    if column is None:
        return []
    return list((await db.execute(
        select(DeliveryChecklistItem).where(
            column == value,
            DeliveryChecklistItem.target_audience == target_audience,
        )
        .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
    )).scalars().all())


async def list_checklist_items(
    db: AsyncSession, *,
    program_id: UUID | None = None, cohort_id: UUID | None = None, session_id: UUID | None = None,
    role_id: UUID | None = None,
    target_audience: str = "instructor",
) -> list[DeliveryChecklistItem]:
    """One (level, role, target_audience) bucket — no inheritance, no role fallback applied."""
    items = await _items_at_level(
        db, program_id=program_id, cohort_id=cohort_id, session_id=session_id,
        target_audience=target_audience,
    )
    return [i for i in items if i.role_id == role_id]


async def set_checklist_items(
    db: AsyncSession, *, lines: list[dict], actor_user_id: UUID,
    program_id: UUID | None = None, cohort_id: UUID | None = None, session_id: UUID | None = None,
    role_id: UUID | None = None,
    target_audience: str = "instructor",
) -> list[DeliveryChecklistItem]:
    """Replace one (level, role, target_audience) bucket wholesale."""
    owners = [program_id, cohort_id, session_id]
    if sum(1 for o in owners if o is not None) != 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="A checklist belongs to exactly one of a program, a cohort or a session",
        )

    existing = await list_checklist_items(
        db, program_id=program_id, cohort_id=cohort_id, session_id=session_id, role_id=role_id,
        target_audience=target_audience,
    )
    for item in existing:
        await db.delete(item)
    await db.flush()

    out = []
    for i, line in enumerate(lines):
        title = (line.get("title") or "").strip()
        if not title:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="A checklist item needs a title")

        raw_attachments = line.get("attachments") or []
        attachments = []
        for att in raw_attachments:
            if isinstance(att, dict):
                mat_id = att.get("material_id")
                attachments.append({
                    "id": str(att.get("id") or uuid4()),
                    "type": att.get("type") or ("material" if mat_id else "link"),
                    "material_id": str(mat_id) if mat_id else None,
                    "title": att.get("title"),
                    "url": att.get("url"),
                })
            elif hasattr(att, "model_dump"):
                d = att.model_dump()
                mat_id = d.get("material_id")
                attachments.append({
                    "id": str(d.get("id") or uuid4()),
                    "type": d.get("type") or ("material" if mat_id else "link"),
                    "material_id": str(mat_id) if mat_id else None,
                    "title": d.get("title"),
                    "url": d.get("url"),
                })

        mat_id = line.get("material_id")
        link_u = line.get("link_url")
        if not attachments:
            if mat_id:
                attachments.append({
                    "id": str(uuid4()),
                    "type": "material",
                    "material_id": str(mat_id),
                    "title": None,
                    "url": None,
                })
            if link_u:
                attachments.append({
                    "id": str(uuid4()),
                    "type": "link",
                    "material_id": None,
                    "title": link_u,
                    "url": link_u,
                })

        primary_mat_id = mat_id
        primary_link_url = link_u
        if not primary_mat_id:
            for a in attachments:
                if a.get("type") == "material" and a.get("material_id"):
                    try:
                        primary_mat_id = UUID(str(a["material_id"]))
                        break
                    except (ValueError, TypeError):
                        pass
        if not primary_link_url:
            for a in attachments:
                if a.get("type") == "link" and a.get("url"):
                    primary_link_url = a["url"]
                    break

        item = DeliveryChecklistItem(
            id=uuid4(), program_id=program_id, cohort_id=cohort_id, session_id=session_id, role_id=role_id,
            target_audience=target_audience,
            material_id=primary_mat_id,
            link_url=primary_link_url,
            attachments=attachments,
            title=title, description=line.get("description"),
            requires_proof=bool(line.get("requires_proof")),
            is_required=bool(line.get("is_required", True)),
            sort_order=int(line.get("sort_order") or (i + 1)),
            created_by=actor_user_id,
        )
        db.add(item)
        out.append(item)
    await db.flush()
    return out


async def _instructor_role(db: AsyncSession, session_id: UUID, user_id: UUID) -> UUID | None:
    """Which role this instructor holds on this session — what `resolve_checklist`
    needs to pick their bucket over the general one. `None` for someone with no
    `SessionInstructor` row (shouldn't happen for a deliverable session, but
    resolving to the general checklist rather than raising is the safer default)."""
    return await db.scalar(
        select(SessionInstructor.role_id).where(
            SessionInstructor.session_id == session_id, SessionInstructor.user_id == user_id,
        )
    )


async def resolve_checklist(
    db: AsyncSession, session: Session, role_id: UUID | None = None,
) -> list[DeliveryChecklistItem]:
    """What this instructor actually works through on this session.

    Two overrides stacked, both **override, not merge**:

    * **Level** — the nearest of session -> cohort -> program with *anything*
      set at all wins outright; a level with nothing set is skipped entirely,
      not treated as "zero items."
    * **Role**, within whichever level wins — that role's own items if any
      exist there, else that level's general (role_id IS NULL) items. A role
      checklist replaces the general one for that role; it is never added on
      top of it.

    Merging either axis would make it impossible to *remove* an item for one
    cohort or one role, which is exactly what overridable has to mean (see
    `materials.py` for the level half of this reasoning).

    Returns `[]`, not a fabricated default, when nothing is configured
    anywhere — a checklist item's id is a real foreign key
    (`InstructorChecklistProgress.checklist_item_id`), so any placeholder
    item not backed by a `delivery_checklist_items` row would 500 the
    instant an instructor tried to check it off.
    """
    # 1. Session level
    items = await _items_at_level(db, session_id=session.id)
    if items:
        role_items = [i for i in items if i.role_id == role_id] if role_id is not None else []
        if role_items:
            return role_items
        general = [i for i in items if i.role_id is None]
        if general:
            return general

    # 2. Template session fallback
    cohort = await db.get(Cohort, session.cohort_id)
    if cohort is not None:
        template_cohort = await db.scalar(
            select(Cohort).where(
                Cohort.program_id == cohort.program_id,
                Cohort.name.ilike("%template%"),
                Cohort.id != cohort.id,
            ).order_by(Cohort.created_at.asc())
        )
        if template_cohort is not None:
            all_sessions = (await db.execute(
                select(Session.id).where(Session.cohort_id == cohort.id)
                .order_by(Session.meeting_date, Session.starts_at)
            )).scalars().all()
            try:
                s_idx = all_sessions.index(session.id)
                t_sessions = (await db.execute(
                    select(Session.id).where(Session.cohort_id == template_cohort.id)
                    .order_by(Session.meeting_date, Session.starts_at)
                )).scalars().all()
                if s_idx < len(t_sessions):
                    t_items = await _items_at_level(db, session_id=t_sessions[s_idx])
                    if t_items:
                        role_items = [i for i in t_items if i.role_id == role_id] if role_id is not None else []
                        if role_items:
                            return role_items
                        general = [i for i in t_items if i.role_id is None]
                        if general:
                            return general
            except ValueError:
                pass

        # 3. Cohort level
        cohort_items = await _items_at_level(db, cohort_id=cohort.id)
        if cohort_items:
            role_items = [i for i in cohort_items if i.role_id == role_id] if role_id is not None else []
            if role_items:
                return role_items
            general = [i for i in cohort_items if i.role_id is None]
            if general:
                return general

        # 4. Program level
        program_items = await _items_at_level(db, program_id=cohort.program_id)
        role_items = [i for i in program_items if i.role_id == role_id] if role_id is not None else []
        if role_items:
            return role_items
        return [i for i in program_items if i.role_id is None]

    return []


async def resolve_internal_checklist(
    db: AsyncSession, session: Session
) -> list[DeliveryChecklistItem]:
    """Resolves operational / internal checklist items for a session.
    Overrides program -> cohort -> session, exactly mirroring materials and instructor checklist.
    """
    # 1. Session level
    items = await _items_at_level(db, session_id=session.id, target_audience="internal")
    if items:
        return items

    # 2. Template session fallback
    cohort = await db.get(Cohort, session.cohort_id)
    if cohort is not None:
        template_cohort = await db.scalar(
            select(Cohort).where(
                Cohort.program_id == cohort.program_id,
                Cohort.name.ilike("%template%"),
                Cohort.id != cohort.id,
            ).order_by(Cohort.created_at.asc())
        )
        if template_cohort is not None:
            all_sessions = (await db.execute(
                select(Session.id).where(Session.cohort_id == cohort.id)
                .order_by(Session.meeting_date, Session.starts_at)
            )).scalars().all()
            try:
                s_idx = all_sessions.index(session.id)
                t_sessions = (await db.execute(
                    select(Session.id).where(Session.cohort_id == template_cohort.id)
                    .order_by(Session.meeting_date, Session.starts_at)
                )).scalars().all()
                if s_idx < len(t_sessions):
                    t_items = await _items_at_level(db, session_id=t_sessions[s_idx], target_audience="internal")
                    if t_items:
                        return t_items
            except ValueError:
                pass

        # 3. Cohort level
        cohort_items = await _items_at_level(db, cohort_id=cohort.id, target_audience="internal")
        if cohort_items:
            return cohort_items

        # 4. Program level
        program_items = await _items_at_level(db, program_id=cohort.program_id, target_audience="internal")
        if program_items:
            return program_items

    return []


async def hydrate_checklist_attachments(
    db: AsyncSession, items: list[DeliveryChecklistItem], *, is_ops: bool = False
) -> dict[UUID, list[dict]]:
    from app.models.sessions.material import Material
    from app.services.sessions import materials as mat_svc

    # 1. Collect all material IDs
    material_ids = set()
    for item in items:
        att_list = item.attachments or []
        for a in att_list:
            if isinstance(a, dict) and a.get("type") == "material" and a.get("material_id"):
                try:
                    material_ids.add(UUID(str(a["material_id"])))
                except (ValueError, TypeError):
                    pass
        if item.material_id:
            material_ids.add(item.material_id)

    materials_by_id = {}
    if material_ids:
        m_rows = (await db.execute(
            select(Material).where(Material.id.in_(list(material_ids)))
        )).scalars().all()
        for m in m_rows:
            materials_by_id[m.id] = m

    # 2. Build hydrated attachments map
    hydrated_by_item: dict[UUID, list[dict]] = {}
    for item in items:
        res = []
        att_list = list(item.attachments or [])
        # If attachments is empty but legacy columns present, synthesize
        if not att_list:
            if item.material_id:
                att_list.append({"type": "material", "material_id": str(item.material_id)})
            if item.link_url:
                att_list.append({"type": "link", "url": item.link_url, "title": item.link_url})

        for att in att_list:
            if not isinstance(att, dict):
                continue
            att_type = att.get("type") or "link"
            att_id = att.get("id") or str(uuid4())
            if att_type == "material":
                m_id_str = att.get("material_id")
                m_obj = None
                if m_id_str:
                    try:
                        m_obj = materials_by_id.get(UUID(str(m_id_str)))
                    except (ValueError, TypeError):
                        pass
                if m_obj:
                    is_published = bool(m_obj.is_published)
                    has_access = is_ops or is_published
                    url = await mat_svc.material_url(m_obj) if has_access else None
                    access_denied_message = (
                        None if has_access
                        else "You don't have access to this document, please contact the operations team."
                    )
                    res.append({
                        "id": att_id,
                        "type": "material",
                        "material_id": str(m_obj.id),
                        "title": m_obj.title,
                        "url": url,
                        "is_file": bool(m_obj.file_path),
                        "is_published": is_published,
                        "has_access": has_access,
                        "access_denied_message": access_denied_message,
                    })
                else:
                    res.append({
                        "id": att_id,
                        "type": "material",
                        "material_id": m_id_str,
                        "title": att.get("title") or "Document",
                        "url": None,
                        "is_file": False,
                        "is_published": False,
                        "has_access": False,
                        "access_denied_message": "Document not found",
                    })
            else:
                # Link
                url = att.get("url")
                title = att.get("title") or url
                res.append({
                    "id": att_id,
                    "type": "link",
                    "material_id": None,
                    "title": title,
                    "url": url,
                    "is_file": False,
                    "is_published": True,
                    "has_access": True,
                    "access_denied_message": None,
                })
        hydrated_by_item[item.id] = res

    return hydrated_by_item


async def get_internal_checklist_for_session(
    db: AsyncSession, session_id: UUID
) -> list[dict]:
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Session not found")

    items = await resolve_internal_checklist(db, session)
    if not items:
        return []

    hydrated_attachments = await hydrate_checklist_attachments(db, items, is_ops=True)

    item_ids = [i.id for i in items]
    progress_rows = (await db.execute(
        select(SessionOpsChecklistProgress).where(
            SessionOpsChecklistProgress.session_id == session_id,
            SessionOpsChecklistProgress.checklist_item_id.in_(item_ids),
        )
    )).scalars().all()
    progress_by_item = {p.checklist_item_id: p for p in progress_rows}

    # Material resolution for legacy material_id
    material_ids = [i.material_id for i in items if i.material_id]
    materials_by_id = {}
    if material_ids:
        from app.models.sessions.material import Material
        m_rows = (await db.execute(
            select(Material).where(Material.id.in_(material_ids))
        )).scalars().all()
        from app.services.sessions import materials as mat_svc
        for m in m_rows:
            materials_by_id[m.id] = {
                "title": m.title,
                "url": await mat_svc.material_url(m),
                "is_file": bool(m.file_path),
            }

    user_ids = [p.completed_by for p in progress_rows if p.completed_by]
    user_names = {}
    if user_ids:
        u_rows = (await db.execute(
            select(User).where(User.id.in_(user_ids))
        )).scalars().all()
        user_names = {u.id: u.full_name or u.email for u in u_rows}

    report_ids = [p.proof_report_id for p in progress_rows if p.proof_report_id]
    proof_urls = {}
    if report_ids:
        r_rows = (await db.execute(
            select(SessionReport).where(SessionReport.id.in_(report_ids))
        )).scalars().all()
        for r in r_rows:
            proof_urls[r.id] = await resolve_report_url(r.file_ref)

    out = []
    for item in items:
        prog = progress_by_item.get(item.id)
        mat_info = materials_by_id.get(item.material_id) if item.material_id else None
        item_atts = hydrated_attachments.get(item.id, [])
        out.append({
            "item_id": item.id,
            "title": item.title,
            "description": item.description,
            "requires_proof": item.requires_proof,
            "is_required": item.is_required,
            "sort_order": item.sort_order,
            "target_audience": item.target_audience,
            "material_id": item.material_id,
            "material_title": mat_info["title"] if mat_info else None,
            "material_url": mat_info["url"] if mat_info else None,
            "material_is_file": mat_info["is_file"] if mat_info else False,
            "link_url": item.link_url,
            "attachments": item_atts,
            "is_done": prog.is_done if prog else False,
            "proof_report_id": prog.proof_report_id if prog else None,
            "proof_url": proof_urls.get(prog.proof_report_id) if prog and prog.proof_report_id else None,
            "note": prog.note if prog else None,
            "completed_by": prog.completed_by if prog else None,
            "completed_by_name": user_names.get(prog.completed_by) if prog and prog.completed_by else None,
            "updated_at": prog.updated_at if prog else None,
        })
    return out


async def set_internal_checklist_progress(
    db: AsyncSession,
    session_id: UUID,
    checklist_item_id: UUID,
    actor_user_id: UUID,
    *,
    is_done: bool,
    proof_report_id: UUID | None = None,
    note: str | None = None,
) -> SessionOpsChecklistProgress:
    prog = await db.scalar(
        select(SessionOpsChecklistProgress).where(
            SessionOpsChecklistProgress.session_id == session_id,
            SessionOpsChecklistProgress.checklist_item_id == checklist_item_id,
        )
    )
    if prog is None:
        prog = SessionOpsChecklistProgress(
            id=uuid4(),
            session_id=session_id,
            checklist_item_id=checklist_item_id,
            is_done=is_done,
            proof_report_id=proof_report_id,
            note=note,
            completed_by=actor_user_id if is_done else None,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(prog)
    else:
        prog.is_done = is_done
        if proof_report_id is not None:
            prog.proof_report_id = proof_report_id
        if note is not None:
            prog.note = note
        prog.completed_by = actor_user_id if is_done else None
        prog.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return prog


# ── the instructor's day ────────────────────────────────────────────────────

async def _get_or_create_day(db: AsyncSession, session_id: UUID, user_id: UUID) -> InstructorSessionDay:
    day = (await db.execute(
        select(InstructorSessionDay).where(
            InstructorSessionDay.session_id == session_id,
            InstructorSessionDay.user_id == user_id,
        )
    )).scalars().first()
    if day is None:
        day = InstructorSessionDay(id=uuid4(), session_id=session_id, user_id=user_id, status="draft")
        db.add(day)
        await db.flush()
    return day


def _refuse_if_locked(day: InstructorSessionDay) -> None:
    """An approved day is what ops signed off and what the payment line counts.
    Reopening it is an ops decision (`return_day`), not something an instructor
    can do by editing underneath the approval."""
    if day.status == "approved":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This day is approved — ask ops to reopen it if something needs changing",
        )


async def check_in(
    db: AsyncSession, session_id: UUID, user: User, *,
    att_status: str, reason: str | None = None,
) -> InstructorSessionDay:
    """"I'm here" / "I can't attend today" (§4).

    Recorded day by day and never inferred from the cohort assignment — the
    whole point is that an instructor assigned to five days may legitimately
    miss one, and the letter should say four.
    """
    if att_status not in ATT_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Attendance is 'present' or 'absent'")
    await _get_deliverable_session(db, session_id, user)
    day = await _get_or_create_day(db, session_id, user.id)
    _refuse_if_locked(day)

    day.att_status = att_status
    day.absence_reason = reason if att_status == "absent" else None
    # Idempotent on the timestamp, same reasoning as `start_session`: tapping
    # twice on a flaky connection must not move the recorded arrival time.
    if att_status == "present" and day.checked_in_at is None:
        day.checked_in_at = datetime.now(timezone.utc)
    if att_status == "absent":
        day.checked_in_at = None
    await db.flush()
    return day


async def set_checklist_progress(
    db: AsyncSession, session_id: UUID, user: User, *,
    checklist_item_id: UUID, is_done: bool | None = None,
    proof_report_id: UUID | None = None, note: str | None = None,
) -> InstructorChecklistProgress:
    """Tick an item, attach proof to it, or both."""
    session = await _get_deliverable_session(db, session_id, user)
    day = await _get_or_create_day(db, session_id, user.id)
    _refuse_if_locked(day)

    role_id = await _instructor_role(db, session_id, user.id)
    valid_ids = {i.id for i in await resolve_checklist(db, session, role_id)}
    if checklist_item_id not in valid_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That item isn't on this session's checklist")

    if proof_report_id is not None:
        report = await db.get(SessionReport, proof_report_id)
        if report is None or report.session_id != session_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proof upload not found for this session")

    row = (await db.execute(
        select(InstructorChecklistProgress).where(
            InstructorChecklistProgress.day_id == day.id,
            InstructorChecklistProgress.checklist_item_id == checklist_item_id,
        )
    )).scalars().first()
    if row is None:
        row = InstructorChecklistProgress(
            id=uuid4(), day_id=day.id, checklist_item_id=checklist_item_id,
        )
        db.add(row)
    if is_done is not None:
        row.is_done = is_done
    if proof_report_id is not None:
        row.proof_report_id = proof_report_id
    if note is not None:
        row.note = note
    await db.flush()
    return row


async def _missing_requirements(
    db: AsyncSession, session: Session, day: InstructorSessionDay,
) -> list[str]:
    """What still stands between this day and being submittable.

    Returned as a list rather than raising on the first problem: an instructor
    at 3pm should see everything outstanding at once, not discover it one
    round-trip at a time.
    """
    if day.att_status is None:
        return ["Check in (or declare an absence) before submitting the day"]
    if day.att_status == "absent":
        # An absence has nothing to submit — ops acknowledges it directly.
        return []

    role_id = await _instructor_role(db, session.id, day.user_id)
    items = await resolve_checklist(db, session, role_id)
    progress = {
        p.checklist_item_id: p for p in (await db.execute(
            select(InstructorChecklistProgress).where(InstructorChecklistProgress.day_id == day.id)
        )).scalars().all()
    }
    missing = []
    for item in items:
        row = progress.get(item.id)
        if item.is_required and (row is None or not row.is_done):
            missing.append(f"'{item.title}' isn't ticked")
        elif item.requires_proof and (row is None or row.proof_report_id is None):
            missing.append(f"'{item.title}' needs a photo")
    return missing


async def submit_day(db: AsyncSession, session_id: UUID, user: User, *, notes: str | None = None):
    """Send the day for ops review (§11).

    An absence is the one exception: there's no checklist behind it to
    review, so it's approved the moment it's submitted rather than sitting
    in the ops queue asking for a rubber stamp with nothing behind it.
    `reviewed_by` stays `None` to mark this as a system auto-approval, not
    an ops decision.
    """
    session = await _get_deliverable_session(db, session_id, user)
    day = await _get_or_create_day(db, session_id, user.id)
    _refuse_if_locked(day)

    if notes is not None:
        day.instructor_notes = notes

    missing = await _missing_requirements(db, session, day)
    if missing:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="This day isn't ready to submit: " + "; ".join(missing),
        )

    day.submitted_at = datetime.now(timezone.utc)
    # Clear the previous round's comment — leaving it would make a resubmitted
    # day still look like it had been rejected.
    day.review_comment = None
    if day.att_status == "absent":
        day.status = "approved"
        day.reviewed_at = day.submitted_at
        day.reviewed_by = None
    else:
        day.status = "submitted"
    await db.flush()
    return day


# ── ops review ──────────────────────────────────────────────────────────────

async def _get_day(db: AsyncSession, day_id: UUID) -> InstructorSessionDay:
    day = await db.get(InstructorSessionDay, day_id)
    if day is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Day not found")
    return day


async def approve_day(db: AsyncSession, day_id: UUID, actor_user_id: UUID) -> InstructorSessionDay:
    """Ops signs off a day (§12) — and this is what makes it a paid day.

    Ops can approve at any stage, submitted or not (operator, 2026-08-30):
    the checklist is there so ops has something to look at when reviewing,
    not a precondition for paying someone ops already knows delivered —
    chasing an instructor to retroactively fill in a form for a session
    that's already over helps nobody. Approving before submission stamps
    `att_status='present'` if it was never set at all, since that's the
    other half of what actually makes a day payable
    (`journey.py::_paid_day_session_ids`) and an ops approval here is ops
    vouching that the person showed up. It never overwrites an explicit
    "absent" — reversing that is a separate, deliberate action.
    """
    day = await _get_day(db, day_id)
    if day.status == "approved":
        return day  # idempotent — approving twice is not an error
    if day.att_status is None:
        day.att_status = "present"
    day.status = "approved"
    day.reviewed_at = datetime.now(timezone.utc)
    day.reviewed_by = actor_user_id
    await db.flush()
    return day


async def return_day(
    db: AsyncSession, day_id: UUID, actor_user_id: UUID, *, comment: str,
) -> InstructorSessionDay:
    """Send it back with something to fix (§12).

    A comment is mandatory: "changes required" with no reason is the exact
    thing this replaces from WhatsApp.
    """
    comment = (comment or "").strip()
    if not comment:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail="Say what needs changing when returning a day"
        )
    day = await _get_day(db, day_id)
    day.status = "changes_required"
    day.review_comment = comment
    day.reviewed_at = datetime.now(timezone.utc)
    day.reviewed_by = actor_user_id
    await db.flush()
    return day


async def list_day_reviews(
    db: AsyncSession, *, status_filter: str | None = "submitted",
    cohort_id: UUID | None = None, session_id: UUID | None = None,
) -> list[dict]:
    """The ops queue. Defaults to what needs attention now (`submitted`);
    pass `status_filter=None` for everything, a cohort or a session to
    scope it (the latter is the session's own Report tab — every assigned
    instructor's report, whatever state it's in)."""
    stmt = (
        select(InstructorSessionDay, User, Session, Cohort, Program)
        .join(User, User.id == InstructorSessionDay.user_id)
        .join(Session, Session.id == InstructorSessionDay.session_id)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
        .order_by(Session.meeting_date.asc(), User.full_name.asc())
    )
    if status_filter:
        stmt = stmt.where(InstructorSessionDay.status == status_filter)
        if status_filter == "submitted":
            # An absence is auto-approved on submit (see `submit_day`) and so
            # should never reach this state going forward — excluded here as
            # a defensive filter against any pre-existing row that predates
            # that change, so it never shows up asking for review it doesn't
            # need.
            stmt = stmt.where(InstructorSessionDay.att_status != "absent")
    if cohort_id is not None:
        stmt = stmt.where(Session.cohort_id == cohort_id)
    if session_id is not None:
        stmt = stmt.where(Session.id == session_id)
    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    day_ids = [d.id for d, _u, _s, _c, _p in rows]
    done_counts = dict((await db.execute(
        select(InstructorChecklistProgress.day_id, func.count())
        .where(
            InstructorChecklistProgress.day_id.in_(day_ids),
            InstructorChecklistProgress.is_done.is_(True),
        )
        .group_by(InstructorChecklistProgress.day_id)
    )).all())

    out = []
    for day, user, session, cohort, program in rows:
        role_id = await _instructor_role(db, session.id, user.id)
        total = len(await resolve_checklist(db, session, role_id))
        out.append({
            "day_id": day.id,
            "session_id": session.id,
            "cohort_id": cohort.id,
            "cohort_name": cohort.name,
            "program_name": program.name,
            "session_title": session.title,
            "meeting_date": session.meeting_date,
            "user_id": user.id,
            "full_name": user.full_name,
            "att_status": day.att_status,
            "absence_reason": day.absence_reason,
            "checked_in_at": day.checked_in_at,
            "status": day.status,
            "submitted_at": day.submitted_at,
            "review_comment": day.review_comment,
            "instructor_notes": day.instructor_notes,
            "checklist_done": done_counts.get(day.id, 0),
            "checklist_total": total,
        })
    return out


async def get_day_detail(db: AsyncSession, session_id: UUID, user: User, *, for_user_id: UUID | None = None) -> dict:
    """One instructor's day, with the resolved checklist and their progress —
    what both the instructor's own portal and the ops review card render."""
    session = await _get_deliverable_session(db, session_id, user)
    target_id = for_user_id or user.id
    day = await _get_or_create_day(db, session_id, target_id)

    role_id = await _instructor_role(db, session_id, target_id)
    items = await resolve_checklist(db, session, role_id)
    is_ops = any(r in user.role_values for r in ("operations", "admin", "facilitator"))
    hydrated_attachments = await hydrate_checklist_attachments(db, items, is_ops=is_ops)
    progress = {
        p.checklist_item_id: p for p in (await db.execute(
            select(InstructorChecklistProgress).where(InstructorChecklistProgress.day_id == day.id)
        )).scalars().all()
    }

    checklist = []
    for item in items:
        row = progress.get(item.id)
        proof_url = None
        if row is not None and row.proof_report_id is not None:
            report = await db.get(SessionReport, row.proof_report_id)
            if report is not None:
                proof_url = await resolve_report_url(report)
        checklist.append({
            "item_id": item.id,
            "title": item.title,
            "description": item.description,
            "requires_proof": item.requires_proof,
            "is_required": item.is_required,
            "sort_order": item.sort_order,
            "is_done": bool(row and row.is_done),
            "note": row.note if row else None,
            "proof_report_id": row.proof_report_id if row else None,
            "proof_url": proof_url,
            "attachments": hydrated_attachments.get(item.id, []),
        })

    missing = await _missing_requirements(db, session, day)
    return {
        "day_id": day.id,
        "session_id": session_id,
        "user_id": target_id,
        "att_status": day.att_status,
        "absence_reason": day.absence_reason,
        "checked_in_at": day.checked_in_at,
        "status": day.status,
        "submitted_at": day.submitted_at,
        "reviewed_at": day.reviewed_at,
        "review_comment": day.review_comment,
        "instructor_notes": day.instructor_notes,
        "checklist": checklist,
        "can_submit": not missing,
        "missing": missing,
    }


# ── cohort auto-completion ──────────────────────────────────────────────────

async def cohort_is_fully_reviewed(db: AsyncSession, cohort_id: UUID) -> bool:
    """Every session delivered and every instructor-day signed off.

    Three conditions, all necessary:
      * the cohort has sessions at all;
      * every one of them has `completed_at` set;
      * somebody was actually staffed, and every day row is `approved`.

    The staffing check is not redundant. Without it a cohort nobody was ever
    assigned to has zero day rows, "all approved" is vacuously true, and the
    cohort would complete itself the moment its last session was marked done.
    """
    session_ids = list((await db.execute(
        select(Session.id).where(Session.cohort_id == cohort_id)
    )).scalars().all())
    if not session_ids:
        return False

    unfinished = await db.scalar(
        select(func.count()).select_from(Session)
        .where(Session.cohort_id == cohort_id, Session.completed_at.is_(None))
    )
    if unfinished:
        return False

    staffed = await db.scalar(
        select(func.count()).select_from(SessionInstructor)
        .where(SessionInstructor.session_id.in_(session_ids))
    )
    if not staffed:
        return False

    days = (await db.execute(
        select(InstructorSessionDay.status)
        .where(InstructorSessionDay.session_id.in_(session_ids))
    )).scalars().all()
    # One row per assigned instructor per session, all approved. Fewer rows
    # than assignments means somebody never submitted their day.
    if len(days) < staffed:
        return False
    return all(s == "approved" for s in days)


async def maybe_complete_cohort(db: AsyncSession, cohort_id: UUID, actor_user_id: UUID) -> bool:
    """Flip a cohort to completed once its last day is approved.

    Reuses `complete_cohort()` unchanged — student statuses, the LMS
    certificate gate and student certificates all behave exactly as they do
    when ops presses the button today. The only new thing is who presses it.
    Returns whether it fired, so the caller can report it.

    Does *not* touch payment letters (2026-08-30, reversing an earlier
    decision): a completed cohort's delivered sessions simply become billable
    — they show up on the payments to-do list via `unbilled_sessions` exactly
    as before — but nothing gets drafted until ops actually clicks "Create
    letter". Auto-drafting the moment the last report was approved meant a
    letter existed before anyone decided it should, which is the opposite of
    what "draft" is supposed to mean here.
    """
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None or cohort.status == "completed":
        return False
    if not await cohort_is_fully_reviewed(db, cohort_id):
        return False
    await complete_cohort(db, cohort_id, actor_user_id)
    return True


async def _instructor_breakdown(db: AsyncSession, session: Session) -> list[dict]:
    """Every instructor assigned to this session and where they stand —
    checked in or not, how much of their checklist is done, and whether
    they've submitted — so a Running card on the board can show it without
    anyone opening the session."""
    rows = (await db.execute(
        select(SessionInstructor, User)
        .join(User, User.id == SessionInstructor.user_id)
        .where(SessionInstructor.session_id == session.id)
    )).all()
    if not rows:
        return []

    days = {
        d.user_id: d for d in (await db.execute(
            select(InstructorSessionDay).where(InstructorSessionDay.session_id == session.id)
        )).scalars().all()
    }
    done_counts = {}
    day_ids = [d.id for d in days.values()]
    if day_ids:
        done_counts = dict((await db.execute(
            select(InstructorChecklistProgress.day_id, func.count())
            .where(
                InstructorChecklistProgress.day_id.in_(day_ids),
                InstructorChecklistProgress.is_done.is_(True),
            )
            .group_by(InstructorChecklistProgress.day_id)
        )).all())

    out = []
    for si, user in rows:
        day = days.get(user.id)
        total = len(await resolve_checklist(db, session, si.role_id))
        out.append({
            "user_id": user.id,
            "full_name": user.full_name,
            "checklist_done": done_counts.get(day.id, 0) if day else 0,
            "checklist_total": total,
            "att_status": day.att_status if day else None,
            "checked_in_at": day.checked_in_at if day else None,
            "day_status": day.status if day else None,
        })
    return out


# ── the ops session board (2026-08-28) ──────────────────────────────────────
#
# "What needs review, what's running, what's done" across every cohort at
# once — the thing This Week only half answers (staffing gaps for the next
# 7 days, plus the review queue, but nothing about session lifecycle and
# nothing beyond a week). Needs Review is deliberately not reproduced here:
# it's exactly `list_day_reviews(status_filter="submitted")`, already its
# own endpoint, and the board's frontend calls that directly rather than
# this function returning the same rows a second way. An "Upcoming" column
# used to sit alongside these (2026-08-28) but never earned its keep — a
# session that hasn't started needs nothing from ops — so it was dropped
# (2026-08-30).

async def session_board(
    db: AsyncSession, *, done_offset: int = 0, done_limit: int = 5,
) -> dict:
    """Running / Done, unbounded — every cohort, no date window.

    A session's lifecycle here is exactly the two states `started_at`/
    `completed_at` already encode: `completed_at` set is Done; `started_at`
    set and not completed is Running.
    """
    from app.services.sessions.staffing import resolve_session_location_display

    async def _rows(stmt, *, with_instructors: bool = False) -> list[dict]:
        rows = (await db.execute(stmt)).all()
        out = []
        for session, cohort, program in rows:
            location = await resolve_session_location_display(db, session, cohort)
            out.append({
                "session_id": session.id, "cohort_id": cohort.id, "cohort_name": cohort.name,
                "program_name": program.name, "title": session.title,
                "location": location["name"],
                "meeting_date": session.meeting_date, "starts_at": session.starts_at,
                "staffing_status": session.staffing_status,
                "started_at": session.started_at, "completed_at": session.completed_at,
                "instructors": await _instructor_breakdown(db, session) if with_instructors else [],
            })
        return out

    base = (
        select(Session, Cohort, Program)
        .join(Cohort, Cohort.id == Session.cohort_id)
        .join(Program, Program.id == Cohort.program_id)
    )

    running = await _rows(
        base.where(Session.started_at.isnot(None), Session.completed_at.is_(None))
        .order_by(Session.started_at.asc()),
        with_instructors=True,
    )
    done_total = await db.scalar(
        select(func.count()).select_from(Session).where(Session.completed_at.isnot(None))
    ) or 0
    done = await _rows(
        base.where(Session.completed_at.isnot(None))
        .order_by(Session.completed_at.desc())
        .offset(done_offset).limit(done_limit),
        # A session can be marked done while an instructor's own report is
        # still unsubmitted or absent-unreviewed — session completion and
        # instructor-report completion are tracked separately (only the
        # cohort's own auto-completion gate requires every report approved).
        # Without this, that instructor becomes invisible the moment the
        # session leaves Running, since Need Review only lists submitted
        # reports and a plain Done card carries no per-instructor detail.
        with_instructors=True,
    )

    return {"running": running, "done": done, "done_total": done_total}
