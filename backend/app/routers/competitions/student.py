"""Student-facing competition surface — `/competitions/student/*`.
Allows authenticated learners to see their own team's competition results
and qualification status once results are published. Strictly preserves
judge blindness and peer anonymity.
"""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_active_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.competitions import CompetitionStudentResultOut, StudentExcuseLetterStatusOut, UpdateTeamStudentIdsIn
from app.services.competitions.judging import get_student_team_result

router = APIRouter(
    prefix="/competitions/student",
    tags=["competitions-student"],
    dependencies=[Depends(get_current_active_user)],
)


@router.get("/cohorts/{cohort_id}/my-result", response_model=CompetitionStudentResultOut)
async def get_my_cohort_competition_result(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    result = await get_student_team_result(db, cohort_id=cohort_id, user_id=current.id)
    return CompetitionStudentResultOut(**result)


@router.get("/cohorts/{cohort_id}/timing-window")
async def get_cohort_timing_window(
    cohort_id: uuid.UUID,
    checkpoint_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    from app.models.sessions.cohort import Cohort
    from app.services.competitions.timing_windows import (
        filter_windows_for_gate,
        get_current_active_window,
        is_cohort_deadline_passed,
    )
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        from fastapi import HTTPException, status
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    all_windows = cohort.submission_windows or []

    if checkpoint_id is not None:
        target_cid = None if checkpoint_id == "final" else checkpoint_id
        gate_windows = filter_windows_for_gate(all_windows, target_cid)
        active = get_current_active_window(all_windows, checkpoint_id=target_cid)
        deadline_passed = is_cohort_deadline_passed(all_windows, checkpoint_id=target_cid)
        deadline_window = next((w for w in gate_windows if isinstance(w, dict) and w.get("is_deadline")), None)
        return {
            "windows": gate_windows,
            "active_window": active,
            "is_deadline_passed": deadline_passed,
            "deadline_cutoff_at": deadline_window.get("cutoff_at") if deadline_window else None,
        }

    # Default: Final Gate windows at top level + checkpoints map
    final_windows = filter_windows_for_gate(all_windows, None)
    active = get_current_active_window(all_windows, checkpoint_id=None)
    deadline_passed = is_cohort_deadline_passed(all_windows, checkpoint_id=None)
    deadline_window = next((w for w in final_windows if isinstance(w, dict) and w.get("is_deadline")), None)

    # Group checkpoints
    checkpoints_map = {}
    for w in all_windows:
        if isinstance(w, dict) and w.get("checkpoint_id") and w.get("checkpoint_id") != "final":
            cid = str(w["checkpoint_id"])
            if cid not in checkpoints_map:
                cp_windows = filter_windows_for_gate(all_windows, cid)
                cp_active = get_current_active_window(all_windows, checkpoint_id=cid)
                cp_dead_passed = is_cohort_deadline_passed(all_windows, checkpoint_id=cid)
                cp_dead_win = next((cw for cw in cp_windows if isinstance(cw, dict) and cw.get("is_deadline")), None)
                checkpoints_map[cid] = {
                    "windows": cp_windows,
                    "active_window": cp_active,
                    "is_deadline_passed": cp_dead_passed,
                    "deadline_cutoff_at": cp_dead_win.get("cutoff_at") if cp_dead_win else None,
                }

    return {
        "windows": final_windows,
        "all_windows": all_windows,
        "active_window": active,
        "is_deadline_passed": deadline_passed,
        "deadline_cutoff_at": deadline_window.get("cutoff_at") if deadline_window else None,
        "checkpoints": checkpoints_map,
    }


@router.get("/cohorts/{cohort_id}/excuse-letter-status", response_model=StudentExcuseLetterStatusOut)
async def get_student_excuse_letter_status(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Checks whether invitation / excuse letters are enabled for this cohort and returns team info."""
    from app.models.sessions.cohort import Cohort
    from app.models.team import Team, TeamMember
    from app.models.spine.contact import Contact

    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    cfg = cohort.excuse_letter_config or {}
    enabled = bool(cfg.get("enabled", False))

    team = (await db.execute(
        select(Team).join(TeamMember, TeamMember.team_id == Team.id).where(
            Team.cohort_id == cohort_id, TeamMember.user_id == current.id,
        )
    )).scalars().first()

    members_out = []
    my_sid = current.student_id or ""
    my_uni = ""
    team_uni = ""
    if team:
        from app.models.spine.organization import Organization
        members_q = await db.execute(
            select(User).join(TeamMember, TeamMember.user_id == User.id).where(
                TeamMember.team_id == team.id
            )
        )
        for u in members_q.scalars().all():
            sid = u.student_id
            contact = await db.get(Contact, u.contact_id) if u.contact_id else None
            if not sid and contact:
                sid = contact.student_id
            if u.id == current.id and sid:
                my_sid = sid

            u_uni = ""
            org_id = u.organization_id or (contact.organization_id if contact else None)
            if org_id:
                org = await db.get(Organization, org_id)
                if org:
                    u_uni = org.name_latin or org.name_arabic or ""

            if u.id == current.id:
                my_uni = u_uni
            if not team_uni and u_uni:
                team_uni = u_uni

            members_out.append({
                "user_id": str(u.id),
                "full_name": u.full_name,
                "student_id": sid or "",
                "university_name": u_uni,
                "is_me": u.id == current.id,
            })

    return StudentExcuseLetterStatusOut(
        enabled=enabled,
        cohort_name=cohort.name,
        team_id=team.id if team else None,
        team_name=team.name if team else None,
        my_student_id=my_sid,
        my_university_name=my_uni,
        team_university_name=team_uni,
        members=members_out,
    )


@router.post("/cohorts/{cohort_id}/update-team-student-ids")
async def update_team_student_ids(
    cohort_id: uuid.UUID,
    body: UpdateTeamStudentIdsIn,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Allows students to save their own University ID/name and their teammates' details."""
    from app.models.team import Team, TeamMember
    from app.models.spine.contact import Contact
    from app.services.spine.identity import resolve_or_create_organization

    team = (await db.execute(
        select(Team).join(TeamMember, TeamMember.team_id == Team.id).where(
            Team.cohort_id == cohort_id, TeamMember.user_id == current.id,
        )
    )).scalars().first()

    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="You are not part of any team in this cohort")

    team_user_ids = {
        m.user_id
        for m in (await db.execute(select(TeamMember).where(TeamMember.team_id == team.id))).scalars().all()
    }

    for item in body.members:
        try:
            target_uid = uuid.UUID(item["user_id"])
        except (ValueError, KeyError):
            continue
        if target_uid not in team_user_ids:
            continue
        target_u = await db.get(User, target_uid)
        if not target_u:
            continue

        if "student_id" in item:
            new_sid = (item.get("student_id") or "").strip() or None
            target_u.student_id = new_sid
            if target_u.contact_id:
                contact = await db.get(Contact, target_u.contact_id)
                if contact:
                    contact.student_id = new_sid

        if "university_name" in item:
            u_val = (item.get("university_name") or "").strip()
            if u_val:
                org_row = await resolve_or_create_organization(db, u_val, org_type="university")
                target_u.organization_id = org_row.id
                if target_u.contact_id:
                    contact = await db.get(Contact, target_u.contact_id)
                    if contact:
                        contact.organization_id = org_row.id
            else:
                target_u.organization_id = None
                if target_u.contact_id:
                    contact = await db.get(Contact, target_u.contact_id)
                    if contact:
                        contact.organization_id = None

    if body.team_university_name and body.team_university_name.strip():
        t_org = await resolve_or_create_organization(db, body.team_university_name.strip(), org_type="university")
        for mid in team_user_ids:
            u_mem = await db.get(User, mid)
            if u_mem and not u_mem.organization_id:
                u_mem.organization_id = t_org.id
                if u_mem.contact_id:
                    c = await db.get(Contact, u_mem.contact_id)
                    if c:
                        c.organization_id = t_org.id

    await db.commit()
    return {"status": "ok"}


@router.get("/cohorts/{cohort_id}/my-excuse-letter")
async def get_my_cohort_excuse_letter(
    cohort_id: uuid.UUID,
    mode: Literal["team", "individual"] = "team",
    university_name: str | None = None,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_active_user),
):
    """Download official University Excuse Letter for the authenticated student's team."""
    from app.models.sessions.cohort import Cohort
    from app.models.team import Team, TeamMember
    from app.services.competitions import progression as progression_service

    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    cfg = cohort.excuse_letter_config or {}
    if not bool(cfg.get("enabled", False)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Invitation letters are not enabled for this cohort")

    team = (await db.execute(
        select(Team).join(TeamMember, TeamMember.team_id == Team.id).where(
            Team.cohort_id == cohort_id, TeamMember.user_id == current.id,
        )
    )).scalars().first()

    if team is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="You are not part of any team in this cohort")

    single_uid = current.id if mode == "individual" else None
    pdf_bytes = await progression_service.build_team_excuse_letter_pdf(
        db,
        team=team,
        target_cohort=cohort,
        single_user_id=single_uid,
        institution_name_override=university_name,
    )
    clean_name = "".join(c for c in team.name if c.isalnum() or c in (" ", "-", "_")).strip()
    suffix = f"_{current.full_name}" if single_uid else ""
    filename = f"{clean_name}{suffix}_University_Excuse_Letter.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

