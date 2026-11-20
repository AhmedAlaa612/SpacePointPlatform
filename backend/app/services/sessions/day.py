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

from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

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


def _normalize_sub_items(raw: list | None, *, fresh_ids: bool = False) -> list[dict]:
    out: list[dict] = []
    for s in (raw or []):
        if isinstance(s, dict) and s.get("title"):
            out.append({
                "id": str(uuid4()) if fresh_ids else str(s.get("id") or uuid4()),
                "title": str(s.get("title", "")).strip(),
                "is_required": bool(s.get("is_required", True)),
                "requires_proof": bool(s.get("requires_proof", False)),
            })
    return out


async def _validate_proof_reports(
    db: AsyncSession, session_id: UUID, report_ids: list[UUID],
) -> None:
    if not report_ids:
        return
    unique_ids = list(set(report_ids))
    rows = (await db.execute(
        select(SessionReport).where(SessionReport.id.in_(unique_ids))
    )).scalars().all()
    by_id = {r.id: r for r in rows}
    for rid in unique_ids:
        report = by_id.get(rid)
        if report is None or report.session_id != session_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Proof upload not found for this session")


def _merge_sub_item_proofs(
    existing: dict | None, updates: dict[str, UUID | None] | None,
) -> dict[str, str]:
    merged: dict[str, str] = {str(k): str(v) for k, v in (existing or {}).items() if v}
    for k, v in (updates or {}).items():
        key = str(k)
        if v is None:
            merged.pop(key, None)
        else:
            merged[key] = str(v)
    return merged


async def _resolve_report_urls(db: AsyncSession, report_ids: set[UUID]) -> dict[UUID, str]:
    if not report_ids:
        return {}
    rows = (await db.execute(
        select(SessionReport).where(SessionReport.id.in_(list(report_ids)))
    )).scalars().all()
    urls: dict[UUID, str] = {}
    for report in rows:
        urls[report.id] = await resolve_report_url(report)
    return urls


def _extract_sub_item_proof_maps(
    raw_map: dict | None, proof_urls: dict[UUID, str],
) -> tuple[dict[str, str], dict[str, str]]:
    proof_ids_out: dict[str, str] = {}
    urls_out: dict[str, str] = {}
    for sub_id, report_id_str in (raw_map or {}).items():
        if not report_id_str:
            continue
        try:
            rid = UUID(str(report_id_str))
        except (ValueError, TypeError):
            continue
        url = proof_urls.get(rid)
        if url:
            proof_ids_out[str(sub_id)] = str(rid)
            urls_out[str(sub_id)] = url
    return proof_ids_out, urls_out


_UNSET = object()


async def find_program_template_cohort(
    db: AsyncSession, program_id: UUID, *, exclude_cohort_id: UUID | None = None,
) -> Cohort | None:
    """Strict lookup for a program's official template cohort (never matches arbitrary real cohorts)."""
    stmt = select(Cohort).where(
        Cohort.program_id == program_id,
        or_(
            Cohort.status == "draft",
            Cohort.name.ilike("[Template]%"),
            func.lower(func.trim(Cohort.name)) == "template",
        ),
    )
    if exclude_cohort_id is not None:
        stmt = stmt.where(Cohort.id != exclude_cohort_id)
    return await db.scalar(stmt.order_by(Cohort.created_at.asc()))


def clone_delivery_checklist_item(
    src: DeliveryChecklistItem,
    *,
    actor_user_id: UUID,
    program_id: UUID | None = None,
    cohort_id: UUID | None = None,
    session_id: UUID | None = None,
    role_id: Any = _UNSET,
    target_audience: str | None = None,
    sort_order: int | None = None,
) -> DeliveryChecklistItem:
    """Deep-clone a DeliveryChecklistItem onto a new owner with fresh child attachment and sub-item IDs."""
    cloned_attachments = []
    for att in (src.attachments or []):
        if isinstance(att, dict):
            cloned_attachments.append({
                "id": str(uuid4()),
                "type": att.get("type") or "link",
                "material_id": att.get("material_id"),
                "title": att.get("title"),
                "url": att.get("url"),
            })
        else:
            cloned_attachments.append(att)

    return DeliveryChecklistItem(
        id=uuid4(),
        program_id=program_id,
        cohort_id=cohort_id,
        session_id=session_id,
        role_id=src.role_id if role_id is _UNSET else role_id,
        target_audience=target_audience if target_audience is not None else src.target_audience,
        title=src.title,
        description=src.description,
        requires_proof=src.requires_proof,
        is_required=src.is_required,
        sort_order=sort_order if sort_order is not None else src.sort_order,
        material_id=src.material_id,
        link_url=src.link_url,
        attachments=cloned_attachments,
        sub_items=_normalize_sub_items(src.sub_items, fresh_ids=True),
        created_by=actor_user_id,
    )


def _parse_checklist_line_fields(line: dict, fallback_sort_order: int) -> dict[str, Any]:
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

    return {
        "title": title,
        "description": line.get("description"),
        "requires_proof": bool(line.get("requires_proof")),
        "is_required": bool(line.get("is_required", True)),
        "sort_order": int(line.get("sort_order") or fallback_sort_order),
        "material_id": primary_mat_id,
        "link_url": primary_link_url,
        "attachments": attachments,
        "sub_items": _normalize_sub_items(line.get("sub_items"), fresh_ids=False),
    }


def _parse_optional_uuid(raw_id: Any) -> UUID | None:
    if raw_id is None or raw_id == "":
        return None
    if isinstance(raw_id, UUID):
        return raw_id
    try:
        return UUID(str(raw_id))
    except (ValueError, TypeError):
        return None


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
    """Replace one (level, role, target_audience) bucket, updating matching IDs in place to preserve progress."""
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
    existing_by_id = {item.id: item for item in existing}
    kept_ids: set[UUID] = set()

    out = []
    for i, line in enumerate(lines):
        parsed = _parse_checklist_line_fields(line, i + 1)
        parsed_id = _parse_optional_uuid(line.get("id"))
        if parsed_id is not None and parsed_id in existing_by_id and parsed_id not in kept_ids:
            item = existing_by_id[parsed_id]
            for field, val in parsed.items():
                setattr(item, field, val)
            flag_modified(item, "attachments")
            flag_modified(item, "sub_items")
            kept_ids.add(parsed_id)
            out.append(item)
        else:
            item = DeliveryChecklistItem(
                id=uuid4(),
                program_id=program_id,
                cohort_id=cohort_id,
                session_id=session_id,
                role_id=role_id,
                target_audience=target_audience,
                created_by=actor_user_id,
                **parsed,
            )
            db.add(item)
            out.append(item)

    for item in existing:
        if item.id not in kept_ids:
            await db.delete(item)
    await db.flush()

    if session_id is not None:
        sess = await db.get(Session, session_id)
        if sess is not None:
            should_clear = bool(lines) or not await _all_items_at_level(
                db, session_id=session_id, target_audience=target_audience,
            )
            if should_clear:
                if target_audience == "instructor":
                    sess.instructor_checklist_overridden = False
                elif target_audience == "internal":
                    sess.internal_checklist_overridden = False
                await db.flush()

    return out


async def import_checklist_items(
    db: AsyncSession, *,
    source_scope: str,
    source_owner_id: UUID,
    source_role_id: UUID | None = None,
    source_target_audience: str = "instructor",
    item_ids: list[UUID],
    replace_existing: bool = False,
    actor_user_id: UUID,
    program_id: UUID | None = None,
    cohort_id: UUID | None = None,
    session_id: UUID | None = None,
    role_id: UUID | None = None,
    target_audience: str = "instructor",
) -> list[DeliveryChecklistItem]:
    """Import selected delivery checklist items from a source program, cohort, or session."""
    owners = [program_id, cohort_id, session_id]
    if sum(1 for o in owners if o is not None) != 1:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="A checklist belongs to exactly one of a program, a cohort or a session",
        )

    target_kwargs = dict(program_id=program_id, cohort_id=cohort_id, session_id=session_id)
    if not item_ids:
        return await list_checklist_items(
            db, role_id=role_id, target_audience=target_audience, **target_kwargs
        )

    # 1. Fetch source items
    source_col = (
        DeliveryChecklistItem.program_id if source_scope == "programs"
        else DeliveryChecklistItem.cohort_id if source_scope == "cohorts"
        else DeliveryChecklistItem.session_id if source_scope == "sessions"
        else None
    )
    if source_col is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid source scope")

    raw_items = list((await db.execute(
        select(DeliveryChecklistItem).where(
            source_col == source_owner_id,
            DeliveryChecklistItem.target_audience == source_target_audience,
            DeliveryChecklistItem.id.in_(item_ids),
        ).order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
    )).scalars().all())

    # Fallback if source had no items saved directly at that level
    if not raw_items and source_scope == "sessions":
        session = await db.get(Session, source_owner_id)
        if session:
            resolved = await resolve_checklist(db, session, role_id=source_role_id)
            id_set = set(item_ids)
            raw_items = [i for i in resolved if i.id in id_set]
    elif not raw_items and source_scope == "cohorts":
        cohort = await db.get(Cohort, source_owner_id)
        if cohort and cohort.program_id:
            prog_items = await _items_at_level(
                db, program_id=cohort.program_id, target_audience=source_target_audience
            )
            id_set = set(item_ids)
            raw_items = [i for i in prog_items if i.id in id_set]

    if not raw_items:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="No matching checklist items found to import")

    # 2. Existing items on target
    existing = await list_checklist_items(
        db, role_id=role_id, target_audience=target_audience, **target_kwargs
    )
    if replace_existing:
        for item in existing:
            await db.delete(item)
        await db.flush()
        next_sort_order = 1
    else:
        next_sort_order = max([i.sort_order for i in existing], default=0) + 1

    # 3. Create cloned items with fresh child IDs for sub-items and attachments
    for offset, src in enumerate(raw_items):
        db.add(clone_delivery_checklist_item(
            src,
            actor_user_id=actor_user_id,
            program_id=program_id,
            cohort_id=cohort_id,
            session_id=session_id,
            role_id=role_id,
            target_audience=target_audience,
            sort_order=next_sort_order + offset,
        ))

    await db.flush()
    return await list_checklist_items(
        db, role_id=role_id, target_audience=target_audience, **target_kwargs
    )


async def _cohort_sessions_chronological(db: AsyncSession, cohort_id: UUID) -> list[Session]:
    return list((await db.execute(
        select(Session)
        .where(Session.cohort_id == cohort_id)
        .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
    )).scalars().all())


async def _clear_session_audience_progress(
    db: AsyncSession, session_ids: list[UUID] | set[UUID], audiences: list[str],
) -> None:
    sids = list(session_ids)
    if not sids:
        return
    if "instructor" in audiences:
        day_ids = list((await db.execute(
            select(InstructorSessionDay.id).where(InstructorSessionDay.session_id.in_(sids))
        )).scalars().all())
        if day_ids:
            await db.execute(
                sa_delete(InstructorChecklistProgress).where(InstructorChecklistProgress.day_id.in_(day_ids))
            )
    if "internal" in audiences:
        await db.execute(
            sa_delete(SessionOpsChecklistProgress).where(SessionOpsChecklistProgress.session_id.in_(sids))
        )


async def _done_item_ids_by_day(db: AsyncSession, day_ids: list[UUID]) -> dict[UUID, set[UUID]]:
    if not day_ids:
        return {}
    rows = (await db.execute(
        select(InstructorChecklistProgress.day_id, InstructorChecklistProgress.checklist_item_id)
        .where(
            InstructorChecklistProgress.day_id.in_(day_ids),
            InstructorChecklistProgress.is_done.is_(True),
        )
    )).all()
    out: dict[UUID, set[UUID]] = {}
    for day_id, item_id in rows:
        out.setdefault(day_id, set()).add(item_id)
    return out


async def get_cohort_checklists_summary(db: AsyncSession, cohort_id: UUID) -> dict:
    """Return per-session checklist counts, inheritance flags, and active progress flags for a cohort."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    sessions = await _cohort_sessions_chronological(db, cohort_id)
    inherit = getattr(cohort, "inherit_default_checklists", True)

    cohort_pre_items = await _all_items_at_level(db, cohort_id=cohort_id)
    cohort_pre_by_aud: dict[str, list[DeliveryChecklistItem]] = {"instructor": [], "internal": []}
    for item in cohort_pre_items:
        cohort_pre_by_aud.setdefault(item.target_audience, []).append(item)

    prog_pre_by_aud: dict[str, list[DeliveryChecklistItem]] = {"instructor": [], "internal": []}
    tpl_sessions: list[Session] = []
    tpl_items_by_sess_aud: dict[tuple[UUID, str], list[DeliveryChecklistItem]] = {}
    if inherit:
        prog_pre_items = await _all_items_at_level(db, program_id=cohort.program_id)
        for item in prog_pre_items:
            prog_pre_by_aud.setdefault(item.target_audience, []).append(item)
        template_cohort = await find_program_template_cohort(
            db, cohort.program_id, exclude_cohort_id=cohort.id,
        )
        if template_cohort is not None:
            tpl_sessions = await _cohort_sessions_chronological(db, template_cohort.id)
            tpl_session_ids = [ts.id for ts in tpl_sessions]
            if tpl_session_ids:
                tpl_rows = (await db.execute(
                    select(DeliveryChecklistItem)
                    .where(DeliveryChecklistItem.session_id.in_(tpl_session_ids))
                    .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
                )).scalars().all()
                for row in tpl_rows:
                    tpl_items_by_sess_aud.setdefault((row.session_id, row.target_audience), []).append(row)

    session_ids = [s.id for s in sessions]
    direct_by_sess_aud: dict[tuple[UUID, str], list[DeliveryChecklistItem]] = {}
    active_inst_items_by_sid: dict[UUID, set[UUID]] = {}
    active_int_items_by_sid: dict[UUID, set[UUID]] = {}
    approved_inst_sids: set[UUID] = set()

    if session_ids:
        direct_rows = (await db.execute(
            select(DeliveryChecklistItem)
            .where(DeliveryChecklistItem.session_id.in_(session_ids))
            .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
        )).scalars().all()
        for row in direct_rows:
            direct_by_sess_aud.setdefault((row.session_id, row.target_audience), []).append(row)

        inst_prog_rows = (await db.execute(
            select(InstructorSessionDay.session_id, InstructorChecklistProgress.checklist_item_id)
            .join(InstructorChecklistProgress, InstructorChecklistProgress.day_id == InstructorSessionDay.id)
            .where(
                InstructorSessionDay.session_id.in_(session_ids),
                or_(
                    InstructorChecklistProgress.is_done.is_(True),
                    InstructorChecklistProgress.proof_report_id.isnot(None),
                    and_(
                        InstructorChecklistProgress.note.isnot(None),
                        func.trim(InstructorChecklistProgress.note) != "",
                    ),
                    func.coalesce(func.jsonb_array_length(InstructorChecklistProgress.completed_sub_items), 0) > 0,
                ),
            )
        )).all()
        for sid, item_id in inst_prog_rows:
            active_inst_items_by_sid.setdefault(sid, set()).add(item_id)

        int_prog_rows = (await db.execute(
            select(SessionOpsChecklistProgress.session_id, SessionOpsChecklistProgress.checklist_item_id)
            .where(
                SessionOpsChecklistProgress.session_id.in_(session_ids),
                or_(
                    SessionOpsChecklistProgress.is_done.is_(True),
                    SessionOpsChecklistProgress.proof_report_id.isnot(None),
                    and_(
                        SessionOpsChecklistProgress.note.isnot(None),
                        func.trim(SessionOpsChecklistProgress.note) != "",
                    ),
                    func.coalesce(func.jsonb_array_length(SessionOpsChecklistProgress.completed_sub_items), 0) > 0,
                ),
            )
        )).all()
        for sid, item_id in int_prog_rows:
            active_int_items_by_sid.setdefault(sid, set()).add(item_id)

        approved_inst_sids = set((await db.execute(
            select(InstructorSessionDay.session_id)
            .where(
                InstructorSessionDay.session_id.in_(session_ids),
                InstructorSessionDay.status == "approved",
            )
            .distinct()
        )).scalars().all())

    sessions_out = []
    for idx, s in enumerate(sessions):
        res_eff: dict[str, list[DeliveryChecklistItem]] = {}
        res_inherited: dict[str, bool] = {}
        direct_counts: dict[str, int] = {}
        eff_item_ids: dict[str, set[UUID]] = {}
        for aud in ("instructor", "internal"):
            direct_items = direct_by_sess_aud.get((s.id, aud), [])
            direct_counts[aud] = len(direct_items)
            is_overridden = (
                bool(getattr(s, "instructor_checklist_overridden", False))
                if aud == "instructor"
                else bool(getattr(s, "internal_checklist_overridden", False))
            )
            fb: list[DeliveryChecklistItem] = []
            if not is_overridden:
                if inherit and idx < len(tpl_sessions):
                    fb = tpl_items_by_sess_aud.get((tpl_sessions[idx].id, aud), [])
                if not fb:
                    fb = cohort_pre_by_aud.get(aud, [])
                if not fb and inherit:
                    fb = prog_pre_by_aud.get(aud, [])

            if direct_items:
                res_eff[aud] = direct_items
                res_inherited[aud] = False
                eff_ids = {i.id for i in direct_items}
                if aud == "instructor" and not any(i.role_id is None for i in direct_items):
                    eff_ids |= {i.id for i in fb if i.role_id is None}
                eff_item_ids[aud] = eff_ids
            elif is_overridden:
                res_eff[aud] = []
                res_inherited[aud] = False
                eff_item_ids[aud] = set()
            else:
                res_eff[aud] = fb
                res_inherited[aud] = len(fb) > 0
                eff_item_ids[aud] = {i.id for i in fb}

        sessions_out.append({
            "session_id": s.id,
            "day_number": idx + 1,
            "meeting_date": s.meeting_date,
            "starts_at": s.starts_at,
            "title": s.title,
            "instructor_items_count": direct_counts["instructor"],
            "effective_instructor_items_count": len(res_eff["instructor"]),
            "internal_items_count": direct_counts["internal"],
            "effective_internal_items_count": len(res_eff["internal"]),
            "is_instructor_inherited": res_inherited["instructor"],
            "is_internal_inherited": res_inherited["internal"],
            "has_instructor_progress": bool(active_inst_items_by_sid.get(s.id, set()) & eff_item_ids["instructor"]),
            "has_internal_progress": bool(active_int_items_by_sid.get(s.id, set()) & eff_item_ids["internal"]),
            "has_approved_instructor_day": s.id in approved_inst_sids,
        })

    return {
        "cohort_id": cohort.id,
        "pre_workshop_instructor_count": len(cohort_pre_by_aud.get("instructor", [])),
        "pre_workshop_internal_count": len(cohort_pre_by_aud.get("internal", [])),
        "sessions": sessions_out,
    }


async def _all_items_at_level(
    db: AsyncSession, *,
    program_id: UUID | None = None, cohort_id: UUID | None = None, session_id: UUID | None = None,
    target_audience: str | None = None,
) -> list[DeliveryChecklistItem]:
    column = (
        DeliveryChecklistItem.program_id if program_id
        else DeliveryChecklistItem.cohort_id if cohort_id
        else DeliveryChecklistItem.session_id if session_id
        else None
    )
    value = program_id or cohort_id or session_id
    if column is None:
        return []
    stmt = select(DeliveryChecklistItem).where(column == value)
    if target_audience is not None:
        stmt = stmt.where(DeliveryChecklistItem.target_audience == target_audience)
    return list((await db.execute(
        stmt.order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
    )).scalars().all())


async def _resolve_import_source(
    db: AsyncSession,
    target_cohort: Cohort,
    *,
    source_type: str,
    source_id: UUID | None,
) -> tuple[dict[str, list[DeliveryChecklistItem]], list[Session], dict[str, Any]]:
    if source_type == "program":
        src_prog_id = source_id or target_cohort.program_id
        src_program = await db.get(Program, src_prog_id)
        if src_program is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source program not found")
        template_cohort = await find_program_template_cohort(
            db, src_prog_id, exclude_cohort_id=target_cohort.id,
        )
        prog_items = await _all_items_at_level(db, program_id=src_prog_id)
        tpl_cohort_items = (
            await _all_items_at_level(db, cohort_id=template_cohort.id)
            if template_cohort is not None else []
        )
        pre_by_aud: dict[str, list[DeliveryChecklistItem]] = {}
        for aud in ("instructor", "internal"):
            direct = [i for i in prog_items if i.target_audience == aud]
            pre_by_aud[aud] = direct if direct else [i for i in tpl_cohort_items if i.target_audience == aud]
        source_sessions = (
            await _cohort_sessions_chronological(db, template_cohort.id)
            if template_cohort is not None else []
        )
        return pre_by_aud, source_sessions, {"source_type": "program", "program_id": src_prog_id}

    if source_type == "cohort":
        if source_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select a source cohort to import from")
        if source_id == target_cohort.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Cannot import defaults from the same cohort; use Switch Days instead",
            )
        src_cohort = await db.get(Cohort, source_id)
        if src_cohort is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source cohort not found")
        src_inherit = getattr(src_cohort, "inherit_default_checklists", True)
        cohort_items = await _all_items_at_level(db, cohort_id=src_cohort.id)
        prog_items = (
            await _all_items_at_level(db, program_id=src_cohort.program_id)
            if src_inherit else []
        )
        pre_by_aud = {}
        for aud in ("instructor", "internal"):
            direct = [i for i in cohort_items if i.target_audience == aud]
            pre_by_aud[aud] = direct if direct else [i for i in prog_items if i.target_audience == aud]
        source_sessions = await _cohort_sessions_chronological(db, src_cohort.id)
        src_tpl = (
            await find_program_template_cohort(
                db, src_cohort.program_id, exclude_cohort_id=src_cohort.id,
            )
            if src_inherit else None
        )
        src_tpl_sessions = (
            await _cohort_sessions_chronological(db, src_tpl.id)
            if src_tpl is not None else []
        )
        return pre_by_aud, source_sessions, {
            "source_type": "cohort",
            "cohort": src_cohort,
            "template_sessions": src_tpl_sessions,
            "cohort_pre": pre_by_aud,
        }

    raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid source_type")


async def _source_session_items_for_audience(
    db: AsyncSession,
    s_sess: Session,
    s_idx: int,
    aud: str,
    source_meta: dict[str, Any],
) -> list[DeliveryChecklistItem]:
    direct = await _all_items_at_level(db, session_id=s_sess.id, target_audience=aud)
    if direct or source_meta["source_type"] != "cohort":
        return direct
    is_overridden = (
        bool(getattr(s_sess, "instructor_checklist_overridden", False))
        if aud == "instructor"
        else bool(getattr(s_sess, "internal_checklist_overridden", False))
    )
    if is_overridden:
        return []
    tpl_sessions: list[Session] = source_meta.get("template_sessions") or []
    if s_idx < len(tpl_sessions):
        tpl_items = await _all_items_at_level(db, session_id=tpl_sessions[s_idx].id, target_audience=aud)
        if tpl_items:
            return tpl_items
    return list(source_meta["cohort_pre"].get(aud, []))


async def import_cohort_defaults(
    db: AsyncSession,
    *,
    cohort_id: UUID,
    actor_user_id: UUID,
    source_type: str = "program",
    source_id: UUID | None = None,
    include_instructor: bool = True,
    include_internal: bool = True,
    include_pre_workshop: bool = True,
    include_titles: bool = False,
    mode: str = "replace",
    day_mappings: list[dict[str, UUID | None]] | None = None,
    create_missing_sessions: bool = False,
) -> dict:
    """Bulk-materialize checklists from a program default or another cohort onto a target cohort."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    audiences = [aud for aud, enabled in (("instructor", include_instructor), ("internal", include_internal)) if enabled]
    if not audiences:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select at least one checklist audience to import")

    pre_by_aud, source_sessions, source_meta = await _resolve_import_source(
        db, cohort, source_type=source_type, source_id=source_id,
    )

    target_sessions = await _cohort_sessions_chronological(db, cohort.id)
    will_create_sessions = not target_sessions and create_missing_sessions and bool(source_sessions)
    effective_target_sessions = list(target_sessions)

    pairs_plan: list[tuple[Session | None, Session, int]] = []
    if not target_sessions:
        if will_create_sessions:
            for idx, s_src in enumerate(source_sessions):
                pairs_plan.append((None, s_src, idx))
    elif day_mappings is None:
        for idx, (t_sess, s_sess) in enumerate(zip(effective_target_sessions, source_sessions)):
            pairs_plan.append((t_sess, s_sess, idx))
    else:
        target_by_id = {s.id: s for s in effective_target_sessions}
        source_by_id = {s.id: (s, idx) for idx, s in enumerate(source_sessions)}
        seen_targets: set[UUID] = set()
        for m in day_mappings:
            tid = m.get("target_session_id")
            sid = m.get("source_session_id")
            if tid not in target_by_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Target session does not belong to this cohort")
            if tid in seen_targets:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Duplicate target session in day mapping")
            seen_targets.add(tid)
            if sid is None:
                continue
            if sid not in source_by_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Source session does not belong to the chosen source")
            s_sess, s_idx = source_by_id[sid]
            pairs_plan.append((target_by_id[tid], s_sess, s_idx))

    if mode == "replace" and "instructor" in audiences and target_sessions:
        mapped_existing_ids = [t_sess.id for t_sess, _, _ in pairs_plan if t_sess is not None]
        if mapped_existing_ids:
            approved_sid = await db.scalar(
                select(InstructorSessionDay.session_id)
                .where(
                    InstructorSessionDay.session_id.in_(mapped_existing_ids),
                    InstructorSessionDay.status == "approved",
                )
                .limit(1)
            )
            if approved_sid is not None:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    detail=(
                        "Cannot replace instructor checklists on a day that already has an approved "
                        "instructor report. Use 'Fill empty days only' or skip that day."
                    ),
                )

    imported_pre = 0
    if include_pre_workshop:
        for aud in audiences:
            existing_pre = await _all_items_at_level(db, cohort_id=cohort.id, target_audience=aud)
            if mode == "fill_empty" and existing_pre:
                continue
            if mode == "replace" and existing_pre:
                for item in existing_pre:
                    await db.delete(item)
                await db.flush()
            for src in pre_by_aud.get(aud, []):
                db.add(clone_delivery_checklist_item(src, actor_user_id=actor_user_id, cohort_id=cohort.id))
                imported_pre += 1
        await db.flush()

    sessions_created = 0
    pairs: list[tuple[Session, Session, int]] = []
    if will_create_sessions:
        start_date = cohort.starts_on or date.today()
        created_list: list[Session] = []
        for idx, s_src in enumerate(source_sessions):
            new_s = Session(
                id=uuid4(),
                cohort_id=cohort.id,
                meeting_date=start_date + timedelta(days=idx),
                starts_at=s_src.starts_at,
                title=s_src.title or f"Day {idx + 1}",
                duration_hours=s_src.duration_hours if s_src.duration_hours is not None else cohort.duration_hours,
            )
            db.add(new_s)
            created_list.append(new_s)
            sessions_created += 1
        await db.flush()
        for idx, (new_s, s_src) in enumerate(zip(created_list, source_sessions)):
            pairs.append((new_s, s_src, idx))
    else:
        pairs = [(t_sess, s_sess, s_idx) for t_sess, s_sess, s_idx in pairs_plan if t_sess is not None]

    imported_session_items = 0
    sessions_updated = 0
    for t_sess, s_sess, s_idx in pairs:
        updated_this = False
        for aud in audiences:
            existing_sess = await _all_items_at_level(db, session_id=t_sess.id, target_audience=aud)
            if mode == "fill_empty" and existing_sess:
                continue
            src_items = await _source_session_items_for_audience(db, s_sess, s_idx, aud, source_meta)
            if mode == "replace":
                await _clear_session_audience_progress(db, [t_sess.id], [aud])
                if existing_sess:
                    for item in existing_sess:
                        await db.delete(item)
                    await db.flush()
                    updated_this = True
                if aud == "instructor":
                    t_sess.instructor_checklist_overridden = len(src_items) == 0
                elif aud == "internal":
                    t_sess.internal_checklist_overridden = len(src_items) == 0
                if not src_items:
                    updated_this = True
            elif src_items:
                if aud == "instructor":
                    t_sess.instructor_checklist_overridden = False
                elif aud == "internal":
                    t_sess.internal_checklist_overridden = False
            for src in src_items:
                db.add(clone_delivery_checklist_item(src, actor_user_id=actor_user_id, session_id=t_sess.id))
                imported_session_items += 1
                updated_this = True
        if include_titles and s_sess.title:
            t_sess.title = s_sess.title
            updated_this = True
        if updated_this:
            sessions_updated += 1

    await db.flush()
    return {
        "imported_pre_workshop_count": imported_pre,
        "imported_session_items_count": imported_session_items,
        "sessions_updated": sessions_updated,
        "sessions_created": sessions_created,
    }


async def switch_cohort_day_checklists(
    db: AsyncSession,
    *,
    cohort_id: UUID,
    session_plan_order: list[UUID],
    scope: str = "both",
    include_titles: bool = True,
    actor_user_id: UUID,
) -> dict:
    """Swap day checklists (and optionally titles) across fixed chronological session dates."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    sessions = await _cohort_sessions_chronological(db, cohort_id)
    expected_ids = [s.id for s in sessions]
    if (
        len(session_plan_order) != len(expected_ids)
        or len(set(session_plan_order)) != len(expected_ids)
        or set(session_plan_order) != set(expected_ids)
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="session_plan_order must be an exact permutation of this cohort's sessions",
        )

    moved_indices = [i for i, src_id in enumerate(session_plan_order) if src_id != expected_ids[i]]
    if not moved_indices:
        return {"sessions_switched": 0, "items_moved": 0}

    audiences = ["instructor", "internal"] if scope == "both" else [scope]
    involved_ids = {expected_ids[i] for i in moved_indices} | {session_plan_order[i] for i in moved_indices}

    if "instructor" in audiences:
        approved_sid = await db.scalar(
            select(InstructorSessionDay.session_id)
            .where(
                InstructorSessionDay.session_id.in_(list(involved_ids)),
                InstructorSessionDay.status == "approved",
            )
            .limit(1)
        )
        if approved_sid is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    "Cannot switch a day that already has an approved instructor report. "
                    "Reopen it first, or switch Internal team only."
                ),
            )

    # Materialize inherited fallback checklists onto involved sessions first so moving preserves each day's full plan.
    inherit = getattr(cohort, "inherit_default_checklists", True)
    template_cohort = (
        await find_program_template_cohort(db, cohort.program_id, exclude_cohort_id=cohort.id)
        if inherit else None
    )
    template_sessions = (
        await _cohort_sessions_chronological(db, template_cohort.id)
        if template_cohort is not None else []
    )
    cohort_pre_cache: dict[str, list[DeliveryChecklistItem]] = {}
    prog_pre_cache: dict[str, list[DeliveryChecklistItem]] = {}

    for idx, sess in enumerate(sessions):
        if sess.id not in involved_ids:
            continue
        for aud in audiences:
            direct = await _all_items_at_level(db, session_id=sess.id, target_audience=aud)
            if direct:
                continue
            is_overridden = (
                bool(getattr(sess, "instructor_checklist_overridden", False))
                if aud == "instructor"
                else bool(getattr(sess, "internal_checklist_overridden", False))
            )
            if is_overridden:
                continue
            fallback_items: list[DeliveryChecklistItem] = []
            if inherit and idx < len(template_sessions):
                fallback_items = await _all_items_at_level(
                    db, session_id=template_sessions[idx].id, target_audience=aud,
                )
            if not fallback_items:
                if aud not in cohort_pre_cache:
                    cohort_pre_cache[aud] = await _all_items_at_level(
                        db, cohort_id=cohort.id, target_audience=aud,
                    )
                fallback_items = cohort_pre_cache[aud]
            if not fallback_items and inherit:
                if aud not in prog_pre_cache:
                    prog_pre_cache[aud] = await _all_items_at_level(
                        db, program_id=cohort.program_id, target_audience=aud,
                    )
                fallback_items = prog_pre_cache[aud]
            for src in fallback_items:
                db.add(clone_delivery_checklist_item(src, actor_user_id=actor_user_id, session_id=sess.id))
    await db.flush()

    snapshot_rows = list((await db.execute(
        select(DeliveryChecklistItem).where(
            DeliveryChecklistItem.session_id.in_(list(involved_ids)),
            DeliveryChecklistItem.target_audience.in_(audiences),
        )
    )).scalars().all())
    items_by_sess_aud: dict[tuple[UUID, str], list[DeliveryChecklistItem]] = {}
    for row in snapshot_rows:
        items_by_sess_aud.setdefault((row.session_id, row.target_audience), []).append(row)
    titles_by_id = {s.id: s.title for s in sessions}

    await _clear_session_audience_progress(db, involved_ids, audiences)

    items_moved = 0
    for idx in moved_indices:
        dst = sessions[idx]
        src_id = session_plan_order[idx]
        for aud in audiences:
            moved = items_by_sess_aud.get((src_id, aud), [])
            for item in moved:
                item.session_id = dst.id
                items_moved += 1
            if aud == "instructor":
                dst.instructor_checklist_overridden = len(moved) == 0
            elif aud == "internal":
                dst.internal_checklist_overridden = len(moved) == 0
        if include_titles:
            dst.title = titles_by_id[src_id]

    await db.flush()
    return {"sessions_switched": len(moved_indices), "items_moved": items_moved}


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

    if getattr(session, "instructor_checklist_overridden", False):
        return []

    # 2. Template session fallback
    cohort = await db.get(Cohort, session.cohort_id)
    if cohort is not None:
        inherit = getattr(cohort, "inherit_default_checklists", True)
        if inherit:
            template_cohort = await find_program_template_cohort(
                db, cohort.program_id, exclude_cohort_id=cohort.id,
            )
            if template_cohort is not None:
                all_sessions = (await db.execute(
                    select(Session.id).where(Session.cohort_id == cohort.id)
                    .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
                )).scalars().all()
                try:
                    s_idx = all_sessions.index(session.id)
                    t_sessions = (await db.execute(
                        select(Session.id).where(Session.cohort_id == template_cohort.id)
                        .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
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
        if inherit:
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

    if getattr(session, "internal_checklist_overridden", False):
        return []

    # 2. Template session fallback
    cohort = await db.get(Cohort, session.cohort_id)
    if cohort is not None:
        inherit = getattr(cohort, "inherit_default_checklists", True)
        if inherit:
            template_cohort = await find_program_template_cohort(
                db, cohort.program_id, exclude_cohort_id=cohort.id,
            )
            if template_cohort is not None:
                all_sessions = (await db.execute(
                    select(Session.id).where(Session.cohort_id == cohort.id)
                    .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
                )).scalars().all()
                try:
                    s_idx = all_sessions.index(session.id)
                    t_sessions = (await db.execute(
                        select(Session.id).where(Session.cohort_id == template_cohort.id)
                        .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
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
        if inherit:
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

    report_ids: set[UUID] = set()
    for p in progress_rows:
        if p.proof_report_id:
            report_ids.add(p.proof_report_id)
        for rid_str in (p.sub_item_proofs or {}).values():
            try:
                if rid_str:
                    report_ids.add(UUID(str(rid_str)))
            except (ValueError, TypeError):
                pass
    proof_urls = await _resolve_report_urls(db, report_ids)

    out = []
    for item in items:
        prog = progress_by_item.get(item.id)
        mat_info = materials_by_id.get(item.material_id) if item.material_id else None
        item_atts = hydrated_attachments.get(item.id, [])
        sub_proof_ids, sub_proof_urls = _extract_sub_item_proof_maps(
            prog.sub_item_proofs if prog else None, proof_urls,
        )
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
            "sub_items": item.sub_items or [],
            "completed_sub_items": prog.completed_sub_items if prog and prog.completed_sub_items else [],
            "sub_item_proofs": sub_proof_ids,
            "sub_item_proof_urls": sub_proof_urls,
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
    is_done: bool | None = None,
    proof_report_id: UUID | None = None,
    note: str | None = None,
    completed_sub_items: list[str] | None = None,
    sub_item_proofs: dict[str, UUID | None] | None = None,
) -> SessionOpsChecklistProgress:
    check_ids: list[UUID] = []
    if proof_report_id is not None:
        check_ids.append(proof_report_id)
    if sub_item_proofs:
        check_ids.extend(rid for rid in sub_item_proofs.values() if rid is not None)
    await _validate_proof_reports(db, session_id, check_ids)

    clean_note = (note.strip() or None) if note is not None else None

    prog = await db.scalar(
        select(SessionOpsChecklistProgress).where(
            SessionOpsChecklistProgress.session_id == session_id,
            SessionOpsChecklistProgress.checklist_item_id == checklist_item_id,
        )
    )
    if prog is None:
        done_val = bool(is_done) if is_done is not None else False
        prog = SessionOpsChecklistProgress(
            id=uuid4(),
            session_id=session_id,
            checklist_item_id=checklist_item_id,
            is_done=done_val,
            proof_report_id=proof_report_id,
            note=clean_note,
            completed_sub_items=completed_sub_items if completed_sub_items is not None else [],
            sub_item_proofs=_merge_sub_item_proofs(None, sub_item_proofs),
            completed_by=actor_user_id if done_val else None,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(prog)
    else:
        if is_done is not None:
            prog.is_done = is_done
            prog.completed_by = actor_user_id if is_done else None
        if proof_report_id is not None:
            prog.proof_report_id = proof_report_id
        if note is not None:
            prog.note = clean_note
        if completed_sub_items is not None:
            prog.completed_sub_items = completed_sub_items
        if sub_item_proofs is not None:
            prog.sub_item_proofs = _merge_sub_item_proofs(prog.sub_item_proofs, sub_item_proofs)
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
    completed_sub_items: list[str] | None = None,
    sub_item_proofs: dict[str, UUID | None] | None = None,
) -> InstructorChecklistProgress:
    """Tick an item, attach proof to it, or both."""
    session = await _get_deliverable_session(db, session_id, user)
    day = await _get_or_create_day(db, session_id, user.id)
    _refuse_if_locked(day)

    role_id = await _instructor_role(db, session_id, user.id)
    valid_ids = {i.id for i in await resolve_checklist(db, session, role_id)}
    if checklist_item_id not in valid_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="That item isn't on this session's checklist")

    check_ids: list[UUID] = []
    if proof_report_id is not None:
        check_ids.append(proof_report_id)
    if sub_item_proofs:
        check_ids.extend(rid for rid in sub_item_proofs.values() if rid is not None)
    await _validate_proof_reports(db, session_id, check_ids)

    row = (await db.execute(
        select(InstructorChecklistProgress).where(
            InstructorChecklistProgress.day_id == day.id,
            InstructorChecklistProgress.checklist_item_id == checklist_item_id,
        )
    )).scalars().first()
    if row is None:
        row = InstructorChecklistProgress(
            id=uuid4(), day_id=day.id, checklist_item_id=checklist_item_id,
            completed_sub_items=completed_sub_items if completed_sub_items is not None else [],
            sub_item_proofs=_merge_sub_item_proofs(None, sub_item_proofs),
        )
        db.add(row)
    if is_done is not None:
        row.is_done = is_done
    if completed_sub_items is not None:
        row.completed_sub_items = completed_sub_items
    if sub_item_proofs is not None:
        row.sub_item_proofs = _merge_sub_item_proofs(row.sub_item_proofs, sub_item_proofs)
    if proof_report_id is not None:
        row.proof_report_id = proof_report_id
    if note is not None:
        row.note = note.strip() or None
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
        if row and row.note and row.note.strip():
            # A justification comment satisfies the item (including any required photo).
            continue
        if item.is_required and (row is None or not row.is_done):
            missing.append(f"'{item.title}' isn't ticked")
        elif item.requires_proof and (row is None or row.proof_report_id is None):
            missing.append(f"'{item.title}' needs a photo")

        done_subs = set(row.completed_sub_items or []) if row else set()
        sub_proofs = (row.sub_item_proofs or {}) if row else {}
        for sub in (item.sub_items or []):
            if not isinstance(sub, dict):
                continue
            sub_id = str(sub.get("id") or "")
            sub_title = sub.get("title") or "Sub-topic"
            sub_required = sub.get("is_required", True) is not False
            if sub.get("requires_proof") and (sub_required or sub_id in done_subs) and not sub_proofs.get(sub_id):
                missing.append(f"'{item.title} — {sub_title}' needs a photo")
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
    done_by_day = await _done_item_ids_by_day(db, day_ids)

    out = []
    for day, user, session, cohort, program in rows:
        role_id = await _instructor_role(db, session.id, user.id)
        resolved_items = await resolve_checklist(db, session, role_id)
        resolved_ids = {i.id for i in resolved_items}
        done_count = len(done_by_day.get(day.id, set()) & resolved_ids)
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
            "checklist_done": done_count,
            "checklist_total": len(resolved_items),
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

    report_ids: set[UUID] = set()
    for p in progress.values():
        if p.proof_report_id:
            report_ids.add(p.proof_report_id)
        for rid_str in (p.sub_item_proofs or {}).values():
            try:
                if rid_str:
                    report_ids.add(UUID(str(rid_str)))
            except (ValueError, TypeError):
                pass
    proof_urls = await _resolve_report_urls(db, report_ids)

    checklist = []
    for item in items:
        row = progress.get(item.id)
        proof_url = proof_urls.get(row.proof_report_id) if (row and row.proof_report_id) else None
        sub_proof_ids, sub_proof_urls = _extract_sub_item_proof_maps(
            row.sub_item_proofs if row else None, proof_urls,
        )
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
            "sub_items": item.sub_items or [],
            "completed_sub_items": row.completed_sub_items if row and row.completed_sub_items else [],
            "sub_item_proofs": sub_proof_ids,
            "sub_item_proof_urls": sub_proof_urls,
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
    day_ids = [d.id for d in days.values()]
    done_by_day = await _done_item_ids_by_day(db, day_ids)

    out = []
    for si, user in rows:
        day = days.get(user.id)
        resolved_items = await resolve_checklist(db, session, si.role_id)
        resolved_ids = {i.id for i in resolved_items}
        done_count = len(done_by_day.get(day.id, set()) & resolved_ids) if day else 0
        out.append({
            "user_id": user.id,
            "full_name": user.full_name,
            "checklist_done": done_count,
            "checklist_total": len(resolved_items),
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
