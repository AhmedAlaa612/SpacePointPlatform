"""Cohorts CRUD + the operations "registration desk" (V2 R2-3): session
generation, the registrations list, manual (desk) registration, per-session
instructor assignment, and the resend-ticket/cancel/confirm-payment actions.
Every route is gated by require_operations (admin passes automatically — see
core/dependencies.py's RequireRole).

Reuses the existing services rather than reimplementing them:
register()/issue_ticket() from services/sessions/registration.py, and
resolve_or_create_contact() from services/spine/identity.py. The manual
registration flow below is a deliberate near-duplicate of
routers/sessions/public.py's public_register (same resolve-contact +
guardian-relationship + register() + enqueue-ticket-email shape) — public.py
itself must not be edited, so `_ensure_guardian_relationship` is copied
here verbatim rather than imported from a "private" function in another
router module.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta
from html import escape
from typing import Literal

import redis.asyncio as redis
from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.documents.card_id import format_card_id
from sqlalchemy.orm import aliased

from app.core.dependencies import get_current_active_user, require_operations, require_session_delivery
from app.db.session import get_db
from app.models.certificate import Certificate
from app.models.competitions.judging import CompetitionJudge, CompetitionRubric, CompetitionRubricCriterion
from app.models.lms.program import LmsProgram, LmsProgramCohortOverride, LmsProgramItem
from app.models.document_template import DocumentTemplate
from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.sessions.pre_session_quiz import PreSessionQuizAssignment
from app.models.sessions.delivery_role import DeliveryRole
from app.services.documents.certificate import (
    STUDENT_COMPLETION_FALLBACK_BODY, expand_certificate_body_template,
    format_certificate_program_title, generate_completion_certificate_pdf, merge_certificate_pdfs,
)
from app.services.games.realtime import get_realtime_redis_dep, safe_publish_to_run
from app.services.games.runs import close_open_runs_for_session
from app.services.sessions.openings import fully_staffed, lead_role_id
from app.services.sessions.staffing import resolve_session_location_display
from app.services.sessions import variations as var_svc
from app.models.inventory.location import Location
from app.models.inventory.warehouse import Warehouse
from app.models.sessions.attendance import AttendanceRecord
from app.models.sessions.checklist import DeliveryChecklistItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.material import Material
from app.models.sessions.instructor_interest import InstructorInterest
from app.models.sessions.program import Program
from app.models.sessions.program_variation import ProgramVariation, ProgramVariationDay
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session, SessionInstructor
from app.models.sessions.session_report import SessionReport
from app.models.inventory.item import Item
from app.models.inventory.kit import Kit
from app.models.inventory.movement import Movement
from app.models.inventory.session_kit import KitCheck, SessionKit
from app.services.sessions import openings as openings_svc
from app.models.enums import UserRole
from app.models.spine.contact import Contact, ContactRelationship
from app.models.spine.organization import Organization
from app.models.user import User
from app.schemas.sessions.cohorts import (
    AddSessionRequest,
    AssignInstructorRequest,
    BulkActionError,
    BulkActionResult,
    BulkAssignInstructorRequest,
    BulkOpenCallRequest,
    CohortCloneRequest,
    CohortCreate,
    CohortOut,
    CohortUpdate,
    CompleteCohortRequest,
    CompleteCohortResponse,
    GenerateSessionsRequest,
    GenerateSessionsResponse,
    SessionInstructorOut,
    SessionOut,
    UpdateSessionRequest,
)
from app.schemas.sessions.registration_desk import (
    ConfirmPaymentRequest,
    DeskRegistrationRequest,
    RegistrationAttendanceOut,
    RegistrationOut,
)
from app.schemas.sessions.reports import SessionReportOut
from app.services import storage
from app.services.competitions import judging as judging_svc
from app.services.lms import program as lms_program_svc
from app.services.lms.program import PROGRAM_ITEM_PDF_BUCKET
from app.services.notification import create_notification
from app.services.inventory.cohort_kits import resolve_session_kits
from app.services.missions.cohort_access import instructor_cohort_ids, is_cohort_lms_editor
from app.services.org_access import (
    assert_user_eligible_for_cohort_staffing,
    can_manage_cohort_delivery,
    can_read_cohort,
    cohort_organization_id,
    effective_org_roles,
    is_cohort_org_manager,
    is_ops_or_admin,
    is_partner_managed,
    require_cohort_delivery_manager_or_ops,
    require_cohort_manager_or_ops,
    require_cohort_read_or_ops,
    require_registration_manager_or_ops,
    require_session_delivery_manager_or_ops,
    require_session_manager_or_ops,
    require_session_read_or_ops,
)
from app.services.sessions.cohort_seeding import seed_cohort_from_program
from app.services.website_events import resolve_user_organization
from app.services.sessions import day as day_service
from app.services.sessions import delivery
from app.services.sessions import materials as materials_service
from app.services.sessions import staffing as staffing_service
from app.services.sessions import reports as reports_service
from app.services.lms.ops_integration import (
    build_set_password_link, deactivate_registration_enrollments, resolve_user_for_contact,
    restore_completed_cohort_course_access, revoke_completed_cohort_course_access,
    send_registration_onboarding_email, sync_registration_lms,
)
from app.services.sessions.registration import format_cohort_dates, register
from app.services.spine.identity import normalize_user_email, resolve_or_create_contact
from app.schemas.sessions.media_consent import (
    CohortMediaConsentOut,
    CohortMediaConsentSummaryOut,
    MediaConsentManualMatchRequest,
    MediaConsentManualOverrideRequest,
    MediaConsentWebhookRequest,
)
from app.services.sessions.media_consent import (
    get_cohort_consents_summary,
    get_latest_consents_for_registrations,
    ingest_media_consent_webhook,
    manual_link_media_consent,
    manual_override_media_consent,
)
from app.workers.settings import get_arq_redis, safe_enqueue

router = APIRouter(prefix="/sessions", tags=["sessions-cohorts"])


# ── Cohorts CRUD ─────────────────────────────────────────────────────────────

async def _resolve_effective_warehouse(
    db: AsyncSession, *, warehouse_id: uuid.UUID | None, location_id: uuid.UUID | None
) -> Warehouse | None:
    """The warehouse override wins when set. Otherwise, a location with
    exactly one warehouse resolves unambiguously; a location with more than
    one (or no location at all) leaves it for ops to say."""
    if warehouse_id:
        return await db.get(Warehouse, warehouse_id)
    if location_id:
        warehouses = (await db.execute(
            select(Warehouse).where(Warehouse.location_id == location_id, Warehouse.is_active.is_(True))
        )).scalars().all()
        if len(warehouses) == 1:
            return warehouses[0]
    return None


async def _cohort_out(
    db: AsyncSession, cohort: Cohort, program_name: str | None = None, program_code: str | None = None,
    location: Location | None = None, counts: tuple[int, int, int, date | None] | None = None,
    program_is_competition: bool = False, variation_name: str | None = None,
    organization_name: str | None = None,
) -> CohortOut:
    # 2026-09-30: one bad row (e.g. a hand-inserted status outside the
    # CohortStatus literal) used to 500 the entire cohorts list, since a
    # single model_validate failure aborts the whole response. Display it
    # as planned instead — restored right after so nothing persists.
    raw_status = cohort.status
    if raw_status not in ("planned", "registration_open", "running", "completed", "cancelled"):
        cohort.status = "planned"
    try:
        out = CohortOut.model_validate(cohort)
    finally:
        cohort.status = raw_status
    out.program_name = program_name
    out.program_code = program_code
    out.program_is_competition = program_is_competition
    if organization_name is not None:
        out.organization_name = organization_name
    elif cohort.organization_id is not None:
        out.organization_name = await db.scalar(
            select(Organization.name_latin).where(Organization.id == cohort.organization_id)
        )
    if variation_name is not None:
        out.variation_name = variation_name
    elif getattr(cohort, "variation_id", None) is not None:
        out.variation_name = await db.scalar(
            select(ProgramVariation.name).where(ProgramVariation.id == cohort.variation_id)
        )
    if counts is not None:
        out.sessions_count, out.registrations_count, out.unstaffed_count, out.next_session_date = counts
    if location is not None:
        out.location_name = location.name
        out.location_maps_url = location.maps_url

    warehouse = await _resolve_effective_warehouse(
        db, warehouse_id=cohort.warehouse_id, location_id=cohort.location_id
    )
    if warehouse is not None:
        out.effective_warehouse_id = warehouse.id
        out.effective_warehouse_name = warehouse.name
    return out


def _template_cohort_match():
    """Match internal draft/template cohorts created for Program Templates."""
    return or_(
        Cohort.is_template_legacy.is_(True),
        Cohort.status == "draft",
        Cohort.name.ilike("[Template]%"),
        func.lower(func.trim(Cohort.name)) == "template",
    )


def _real_cohort_clauses():
    """SQLAlchemy filter clauses excluding internal program template cohorts."""
    return (
        Cohort.is_template_legacy.is_(False),
        Cohort.status != "draft",
        ~Cohort.name.ilike("[Template]%"),
        func.lower(func.trim(Cohort.name)) != "template",
    )


@router.get("/cohorts", response_model=list[CohortOut])
async def list_cohorts(
    program_id: uuid.UUID | None = Query(None),
    management_mode: Literal["spacepoint", "partner", "all"] = Query("spacepoint"),
    organization_id: uuid.UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    is_ops = is_ops_or_admin(current_user)
    caller_org: Organization | None = None
    if not is_ops:
        if "organization" not in current_user.role_values:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
        caller_org = await resolve_user_organization(db, current_user)
        if caller_org is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Organization account required")
        roles = effective_org_roles(current_user, is_owner=(caller_org.owner_user_id == current_user.id))
        if not any(r in ("owner", "coordinator", "observer") for r in roles):
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
        if organization_id is not None and organization_id != caller_org.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")

    # Correlated scalar subqueries rather than GROUP BY joins: counting
    # sessions and registrations in the same join would multiply the rows
    # against each other and inflate both. These are the numbers the cohorts
    # worklist needs to answer "what needs attention" without N+1 requests.
    sessions_count = (
        select(func.count(Session.id)).where(Session.cohort_id == Cohort.id).scalar_subquery()
    )
    unstaffed_count = (
        select(func.count(Session.id))
        .where(Session.cohort_id == Cohort.id, Session.staffing_status == "unstaffed")
        .scalar_subquery()
    )
    # Cancelled sign-ups don't hold a seat, so they don't count against capacity.
    registrations_count = (
        select(func.count(Registration.id))
        .where(Registration.cohort_id == Cohort.id, Registration.status != "cancelled")
        .scalar_subquery()
    )
    next_session_date = (
        select(func.min(Session.meeting_date))
        .where(Session.cohort_id == Cohort.id, Session.meeting_date >= date.today())
        .scalar_subquery()
    )

    stmt = (
        select(
            Cohort, Program.name, Program.code, Location,
            sessions_count, registrations_count, unstaffed_count, next_session_date,
            Program.program_type, ProgramVariation.name, Organization.name_latin,
        )
        .join(Program, Program.id == Cohort.program_id)
        .outerjoin(Location, Location.id == Cohort.location_id)
        .outerjoin(ProgramVariation, ProgramVariation.id == Cohort.variation_id)
        .outerjoin(Organization, Organization.id == Cohort.organization_id)
        .where(*_real_cohort_clauses())
    )
    if is_ops:
        if management_mode != "all":
            stmt = stmt.where(Cohort.management_mode == management_mode)
        if organization_id is not None:
            stmt = stmt.where(Cohort.organization_id == organization_id)
    else:
        assert caller_org is not None
        stmt = stmt.where(or_(Cohort.organization_id == caller_org.id, Program.organization_id == caller_org.id))
    if program_id is not None:
        stmt = stmt.where(Cohort.program_id == program_id)
    stmt = stmt.order_by(Cohort.created_at.desc())

    rows = (await db.execute(stmt)).all()
    results = [
        await _cohort_out(
            db, cohort, program_name, program_code, location, (sessions, regs, unstaffed, next_date),
            program_is_competition=(program_type == "competition"),
            variation_name=variation_name,
            organization_name=org_name,
        )
        for cohort, program_name, program_code, location, sessions, regs, unstaffed, next_date, program_type, variation_name, org_name in rows
    ]
    if not is_ops:
        for out in results:
            out.warehouse_id = None
            out.effective_warehouse_id = None
            out.effective_warehouse_name = None
            if out.management_mode != "partner":
                out.unstaffed_count = 0
    return results


@router.post("/cohorts", response_model=CohortOut, status_code=status.HTTP_201_CREATED)
async def create_cohort(
    body: CohortCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    program = await db.get(Program, body.program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    if body.organization_id is not None and await db.get(Organization, body.organization_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Organization not found")
    location = await db.get(Location, body.location_id) if body.location_id else None
    if body.location_id and location is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Location not found")
    if body.warehouse_id and await db.get(Warehouse, body.warehouse_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    data = body.model_dump()
    if data.get("organization_id") is None and program.organization_id is not None:
        data["organization_id"] = program.organization_id
    if data.get("management_mode") is None:
        data["management_mode"] = "partner" if program.organization_id is not None else "spacepoint"
    if data["management_mode"] == "partner":
        data["warehouse_id"] = None
    import_default_checklists = data.pop("import_default_checklists", True)
    checklist_source_program_id = data.pop("checklist_source_program_id", None)
    checklist_source_variation_id = data.pop("checklist_source_variation_id", None)
    if import_default_checklists and checklist_source_program_id is not None and checklist_source_program_id != program.id:
        if await db.get(Program, checklist_source_program_id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Checklist source program not found")

    selected_var: ProgramVariation | None = None
    if data.get("variation_id") is not None:
        selected_var = await var_svc.resolve_variation_for_program(db, program.id, data["variation_id"])
    elif import_default_checklists:
        selected_var = await var_svc.resolve_variation_for_program(db, program.id, active_only=True)
        if selected_var is not None:
            data["variation_id"] = selected_var.id

    apply_defaults = bool(import_default_checklists or selected_var is not None)
    data["inherit_default_checklists"] = bool(
        import_default_checklists
        and (checklist_source_program_id is None or checklist_source_program_id == program.id)
    )
    eff_scalars = var_svc.resolve_effective_scalars(program, selected_var if apply_defaults else None)
    if apply_defaults:
        if data.get("capacity") is None and eff_scalars["capacity"] is not None:
            data["capacity"] = eff_scalars["capacity"]
        if data.get("duration_hours") is None and eff_scalars["duration_hours"] is not None:
            data["duration_hours"] = eff_scalars["duration_hours"]
        if data.get("poster_template_url") is None and eff_scalars["poster_template_url"]:
            data["poster_template_url"] = eff_scalars["poster_template_url"]
        if data.get("keep_course_access_after_completion") is None:
            data["keep_course_access_after_completion"] = eff_scalars["keep_course_access_after_completion"]
    elif data.get("keep_course_access_after_completion") is None:
        data["keep_course_access_after_completion"] = program.keep_course_access_after_completion

    cohort = Cohort(id=uuid.uuid4(), **data)
    db.add(cohort)
    await db.flush()

    await seed_cohort_from_program(
        db,
        cohort=cohort,
        program=program,
        selected_var=selected_var,
        apply_defaults=apply_defaults,
        eff_scalars=eff_scalars,
        import_default_checklists=import_default_checklists,
        actor_user_id=current_user.id,
        checklist_source_program_id=checklist_source_program_id,
        checklist_source_variation_id=checklist_source_variation_id,
        ensure_lms_override=False,
    )

    await db.commit()
    await db.refresh(cohort)
    return await _cohort_out(db, cohort, program.name, program.code, location, program_is_competition=program.is_competition)


@router.get("/cohorts/{cohort_id}", response_model=CohortOut)
async def get_cohort(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    is_ops = bool({"operations", "admin", "coo"} & set(current_user.role_values))
    if not is_ops:
        if await can_read_cohort(db, cohort, current_user):
            pass
        elif await is_cohort_lms_editor(db, cohort_id=cohort_id, user=current_user):
            pass
        elif current_user.role == "instructor" or "organization" in current_user.role_values:
            cohort_ids = await instructor_cohort_ids(db, user=current_user)
            if cohort_ids and cohort_id in cohort_ids:
                pass
            else:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
        else:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")

    program = await db.get(Program, cohort.program_id)
    location = await db.get(Location, cohort.location_id) if cohort.location_id else None
    is_comp = bool(
        program and (program.is_competition or (program.program_type or "").lower() in ("competition", "hackathon"))
    )
    out = await _cohort_out(
        db, cohort, program.name if program else None, program.code if program else None, location,
        program_is_competition=is_comp,
    )
    org_id = await cohort_organization_id(db, cohort)
    if org_id is not None:
        from app.models.website_event import WebsiteEvent

        org = await db.get(Organization, org_id)
        if org is not None:
            out.organization_name = org.name_latin
            out.org_capacity_limit = org.max_students_per_cohort if is_partner_managed(cohort) else None
        ev_slug = await db.scalar(
            select(WebsiteEvent.slug).where(WebsiteEvent.cohort_id == cohort.id).limit(1)
        )
        out.linked_event_slug = ev_slug
    if not is_ops:
        out.warehouse_id = None
        out.effective_warehouse_id = None
        out.effective_warehouse_name = None
    return out


@router.patch("/cohorts/{cohort_id}", response_model=CohortOut)
async def update_cohort(
    cohort_id: uuid.UUID,
    body: CohortUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    changes = body.model_dump(exclude_unset=True)
    is_ops = bool({"operations", "admin", "coo"} & set(current_user.role_values))
    if not is_ops:
        if await is_cohort_org_manager(db, cohort, current_user):
            allowed_org_fields = {
                "name", "starts_on", "ends_on", "location", "location_id", "capacity", "notes",
                "visibility", "poster_template_url", "checklist_title_override",
                "keep_course_access_after_completion", "status",
            }
            if is_partner_managed(cohort):
                allowed_org_fields.add("duration_hours")
            if not set(changes.keys()).issubset(allowed_org_fields):
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
            org_id = await cohort_organization_id(db, cohort)
            if is_partner_managed(cohort) and org_id is not None and changes.get("capacity") is not None:
                org = await db.get(Organization, org_id)
                if org and org.max_students_per_cohort is not None and changes["capacity"] > org.max_students_per_cohort:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"Your organization limit is {org.max_students_per_cohort} students per cohort.",
                    )
            if (
                changes.get("location_id") is not None
                and changes["location_id"] != cohort.location_id
            ):
                loc = await db.get(Location, changes["location_id"])
                if loc is None:
                    raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Location not found")
                if org_id is None or loc.organization_id != org_id:
                    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Location does not belong to your organization")
        else:
            is_editor = await is_cohort_lms_editor(db, cohort_id=cohort_id, user=current_user)
            allowed_editor_fields = {"checklist_title_override", "keep_course_access_after_completion"}
            if is_editor and set(changes.keys()).issubset(allowed_editor_fields):
                pass
            else:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Forbidden")
    if changes.get("status") == "completed" and cohort.status != "completed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "Use \"Complete cohort\" to finish this cohort — it settles the "
                "registrations, issues certificates and completes the sessions."
            ),
        )
    if changes.get("location_id") and await db.get(Location, changes["location_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Location not found")
    if changes.get("warehouse_id") and await db.get(Warehouse, changes["warehouse_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    was_planned = cohort.status == "planned"
    old_keep_access = cohort.keep_course_access_after_completion
    for field, value in changes.items():
        if field == "keep_course_access_after_completion" and value is None:
            continue
        setattr(cohort, field, value)

    if (
        cohort.status == "completed"
        and "keep_course_access_after_completion" in changes
        and cohort.keep_course_access_after_completion != old_keep_access
    ):
        if cohort.keep_course_access_after_completion:
            await restore_completed_cohort_course_access(db, cohort)
        else:
            await revoke_completed_cohort_course_access(db, cohort)

    await db.commit()
    await db.refresh(cohort)

    if was_planned and cohort.status == "registration_open":
        await safe_enqueue(arq_redis, "send_cohort_interest_notifications", str(cohort.id))

    program = await db.get(Program, cohort.program_id)
    location = await db.get(Location, cohort.location_id) if cohort.location_id else None
    return await _cohort_out(db, cohort, program.name if program else None, program.code if program else None, location)


@router.delete("/cohorts/{cohort_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cohort(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Only ever deletes a cohort nobody has signed up for.

    registrations.cohort_id cascades, and attendance cascades from there, so
    an unguarded delete would erase real people's sign-up and attendance
    history without warning. Cancelled registrations count too — a cancellation
    is a record of something that happened, not an empty slot. A cohort that
    ran should be set to `cancelled` or `completed`, not deleted.

    Its sessions (and their instructor assignments) do cascade away, which is
    correct: with no registrations there can be no attendance hanging off them.
    """
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    normalized_name = (cohort.name or "").strip().lower()
    if (
        cohort.status == "draft"
        or normalized_name.startswith("[template]")
        or normalized_name == "template"
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                "This is an internal program template cohort and cannot be deleted directly. "
                "Manage template days from Program Setup instead."
            ),
        )

    registration_count = await db.scalar(
        select(func.count()).select_from(Registration).where(Registration.cohort_id == cohort_id)
    )
    if registration_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"This cohort has {registration_count} registration(s) and can't be deleted. "
                "Set its status to cancelled instead — that keeps the students' history."
            ),
        )

    await db.delete(cohort)
    await db.commit()


@router.post("/cohorts/{cohort_id}/clone", response_model=CohortOut, status_code=status.HTTP_201_CREATED)
async def clone_cohort(
    cohort_id: uuid.UUID,
    body: CohortCloneRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    source = await db.get(Cohort, cohort_id)
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    target_program = await db.get(Program, body.program_id)
    if target_program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")
    source_program = await db.get(Program, source.program_id)

    is_source_comp = source_program is not None and source_program.is_competition
    is_target_comp = target_program.is_competition

    new_cohort = Cohort(
        id=uuid.uuid4(),
        program_id=target_program.id,
        variation_id=source.variation_id if target_program.id == source.program_id else None,
        name=body.name.strip(),
        starts_on=body.starts_on,
        ends_on=body.ends_on,
        status="planned",
        keep_course_access_after_completion=target_program.keep_course_access_after_completion,
        pricing_model=source.pricing_model,
        price=source.price,
        completion_rule_type=source.completion_rule_type,
        completion_rule_value=source.completion_rule_value,
        default_certificate_template_id=source.default_certificate_template_id,
        default_team_certificate_template_id=source.default_team_certificate_template_id,
    )
    if "basics" in body.carry:
        new_cohort.location_id = source.location_id
        new_cohort.warehouse_id = source.warehouse_id
        new_cohort.capacity = source.capacity
        new_cohort.duration_hours = source.duration_hours
        new_cohort.visibility = source.visibility
        new_cohort.organization_id = source.organization_id
        new_cohort.poster_template_url = source.poster_template_url
        new_cohort.keep_course_access_after_completion = source.keep_course_access_after_completion
    if "windows" in body.carry and (
        (is_target_comp and is_source_comp)
        or (target_program.id == source.program_id and not is_source_comp)
    ):
        new_cohort.submission_windows = [dict(w) if isinstance(w, dict) else w for w in (source.submission_windows or [])]
    else:
        new_cohort.submission_windows = []
    db.add(new_cohort)
    await db.flush()

    # ── Roles ──
    if "roles" in body.carry:
        source_openings = (await db.execute(
            select(CohortOpening).where(CohortOpening.cohort_id == source.id)
        )).scalars().all()
        for opening in source_openings:
            db.add(CohortOpening(
                id=uuid.uuid4(),
                cohort_id=new_cohort.id,
                role_id=opening.role_id,
                slots=opening.slots,
                amount_aed=opening.amount_aed,
                notes=opening.notes,
                responsibilities_override=opening.responsibilities_override,
                created_by=current_user.id,
            ))
        if source_openings:
            await db.flush()
    else:
        await openings_svc.copy_program_openings_to_cohort(
            db, program_id=target_program.id, cohort_id=new_cohort.id, actor_user_id=current_user.id,
        )

    # ── Assessment ──
    if "assessment" in body.carry:
        source_assignment = await db.scalar(
            select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == source.id)
        )
        if source_assignment is not None:
            db.add(AssessmentCohortAssignment(
                id=uuid.uuid4(),
                cohort_id=new_cohort.id,
                config_id=source_assignment.config_id,
                assigned_by=current_user.id,
            ))
            await db.flush()
    elif target_program.default_assessment_config_id is not None:
        db.add(AssessmentCohortAssignment(
            id=uuid.uuid4(),
            cohort_id=new_cohort.id,
            config_id=target_program.default_assessment_config_id,
            assigned_by=current_user.id,
        ))
        await db.flush()

    # ── Materials ──
    if "materials" in body.carry:
        materials = (await db.execute(
            select(Material).where(Material.cohort_id == source.id)
        )).scalars().all()
        for mat in materials:
            db.add(Material(
                id=uuid.uuid4(),
                program_id=None,
                cohort_id=new_cohort.id,
                session_id=None,
                title=mat.title,
                notes=mat.notes,
                bucket=mat.bucket,
                file_path=mat.file_path,
                url=mat.url,
                sort_order=mat.sort_order,
                is_published=mat.is_published,
                uploaded_by=current_user.id,
            ))
        if materials:
            await db.flush()

    # ── LMS checklist ──
    if "checklist" in body.carry:
        resolved = await lms_program_svc.resolve_cohort_program(db, source.id)
        if resolved is not None:
            source_lms_program, source_items = resolved
            if source_items:
                target_lms = await db.scalar(
                    select(LmsProgram).where(LmsProgram.program_id == target_program.id)
                )
                target_lms_id = target_lms.id if target_lms is not None else source_lms_program.id
                override = LmsProgramCohortOverride(
                    id=uuid.uuid4(), cohort_id=new_cohort.id, lms_program_id=target_lms_id,
                )
                db.add(override)
                await db.flush()
                item_id_map: dict[str, str] = {}
                for item in source_items:
                    copy_id = uuid.uuid4()
                    item_id_map[str(item.id)] = str(copy_id)
                    copy_pdf_path = None
                    if item.pdf_path:
                        data = await storage.download_file(PROGRAM_ITEM_PDF_BUCKET, item.pdf_path)
                        filename = item.pdf_path.rsplit("/", 1)[-1]
                        copy_pdf_path = await storage.upload_to_path(
                            PROGRAM_ITEM_PDF_BUCKET, f"program-items/{copy_id}/{filename}",
                            data, "application/pdf",
                        )
                    db.add(LmsProgramItem(
                        id=copy_id,
                        owner_type="cohort_override",
                        owner_id=override.id,
                        position=item.position,
                        item_type=item.item_type,
                        title=item.title,
                        description=item.description,
                        optional=item.optional,
                        requires_confirmation=item.requires_confirmation,
                        scope=item.scope,
                        course_id=item.course_id,
                        mission_id=item.mission_id,
                        variant_id=item.variant_id,
                        external_url=item.external_url,
                        submission_prompt=item.submission_prompt,
                        submission_field_type=item.submission_field_type,
                        submission_multi_link=item.submission_multi_link,
                        submission_link_labels=item.submission_link_labels,
                        submission_table_config=item.submission_table_config,
                        pdf_path=copy_pdf_path,
                        deadline_at=item.deadline_at,
                        session_date=item.session_date,
                        session_starts_at=item.session_starts_at,
                        session_location=item.session_location,
                        session_meeting_url=item.session_meeting_url,
                        mission_step_key=item.mission_step_key,
                        gated=item.gated,
                        guideline_kind=item.guideline_kind,
                        guideline_url=item.guideline_url,
                        checkpoint_label=item.checkpoint_label,
                        cohort_quiz_template_id=item.cohort_quiz_template_id,
                    ))
                await db.flush()

                # Remap checkpoint IDs in cloned submission windows if windows were also carried
                if "windows" in body.carry and is_target_comp and is_source_comp and new_cohort.submission_windows:
                    from sqlalchemy.orm.attributes import flag_modified
                    remapped_windows = []
                    for w in new_cohort.submission_windows:
                        if isinstance(w, dict) and w.get("checkpoint_id") and str(w["checkpoint_id"]) in item_id_map:
                            remapped_windows.append({**w, "checkpoint_id": item_id_map[str(w["checkpoint_id"])]})
                        else:
                            remapped_windows.append(w)
                    new_cohort.submission_windows = remapped_windows
                    flag_modified(new_cohort, "submission_windows")

        # ── Delivery checklist (cohort-level pre-workshop items) ──
        source_checklist_items = (await db.execute(
            select(DeliveryChecklistItem).where(DeliveryChecklistItem.cohort_id == source.id)
            .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
        )).scalars().all()
        for ci in source_checklist_items:
            db.add(day_service.clone_delivery_checklist_item(
                ci, actor_user_id=current_user.id, cohort_id=new_cohort.id,
            ))
        if source_checklist_items:
            await db.flush()
    # Else: no override — the new cohort naturally inherits the target
    # program's default checklist.

    # ── Competition rubric ──
    # Only copy if both source and target are competitions
    if "rubric" in body.carry and is_target_comp and is_source_comp:
        found = await judging_svc.get_rubric(db, cohort_id=source.id)
        if found is not None:
            source_rubric, source_criteria = found
            new_rubric = CompetitionRubric(
                id=uuid.uuid4(),
                program_id=target_program.id,
                cohort_id=new_cohort.id,
                name=source_rubric.name,
            )
            db.add(new_rubric)
            await db.flush()
            for crit in source_criteria:
                db.add(CompetitionRubricCriterion(
                    id=uuid.uuid4(),
                    rubric_id=new_rubric.id,
                    key=crit.key,
                    label=crit.label,
                    max_points=crit.max_points,
                    position=crit.position,
                    scored_by=crit.scored_by,
                    sub_criteria=crit.sub_criteria,
                ))
            if source_criteria:
                await db.flush()

    # ── Competition judges (SILENT — zero notifications) ──
    # Only copy if both source and target are competitions
    if "judges" in body.carry and is_target_comp and is_source_comp:
        source_judges = (await db.execute(
            select(CompetitionJudge).where(CompetitionJudge.cohort_id == source.id)
        )).scalars().all()
        for judge in source_judges:
            db.add(CompetitionJudge(
                id=uuid.uuid4(),
                cohort_id=new_cohort.id,
                user_id=judge.user_id,
                onboarding_sent_at=None,
            ))
            # Deliberately NO send_judge_onboarding_email call and NO
            # background email enqueue here — silent copy only.
        if source_judges:
            await db.flush()

    await db.commit()
    await db.refresh(new_cohort)
    program = target_program
    location = await db.get(Location, new_cohort.location_id) if new_cohort.location_id else None
    return await _cohort_out(
        db, new_cohort, program.name, program.code, location,
        program_is_competition=program.is_competition,
    )


@router.post("/cohorts/{cohort_id}/complete", response_model=CompleteCohortResponse)
async def complete_cohort(
    cohort_id: uuid.UUID,
    body: CompleteCohortRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
    rt: redis.Redis | None = Depends(get_realtime_redis_dep),
):
    """Complete a cohort (Ops/Admin on any cohort; Org Owner/Coordinator on Mode A partner cohorts only)."""
    cohort = await require_cohort_delivery_manager_or_ops(db, cohort_id, current_user)
    warnings: list[str] = []
    unfinished_session_ids = list((await db.execute(
        select(Session.id).where(Session.cohort_id == cohort_id, Session.completed_at.is_(None))
    )).scalars().all())
    if await reports_service.report_count_for_cohort(db, cohort_id) == 0:
        warnings.append("No session reports were uploaded for this cohort.")
    unreviewed = await day_service.list_day_reviews(db, status_filter="submitted", cohort_id=cohort_id)
    if unreviewed:
        if is_partner_managed(cohort) and not is_ops_or_admin(current_user):
            warnings.append(f"{len(unreviewed)} workshop day(s) are still awaiting review.")
        else:
            warnings.append(
                f"{len(unreviewed)} workshop day(s) are still awaiting review — "
                "those days won't be counted on anyone's payment letter."
            )
    if unfinished_session_ids:
        warnings.append(
            f"{len(unfinished_session_ids)} session(s) had not been marked done — "
            "they have been completed now."
        )

    send_certificates = body.send_certificates if body else False
    cohort = await delivery.complete_cohort(
        db, cohort_id, current_user.id, send_certificates=send_certificates,
    )
    # A session that just went from Scheduled to Completed can still have a
    # quiz sitting in a lobby, and nobody is going back to press End on a
    # class that went home weeks ago — same reasoning as the instructor's
    # mark-done path in routers/sessions/delivery.py.
    closed: list[uuid.UUID] = []
    for session_id in unfinished_session_ids:
        closed.extend(await close_open_runs_for_session(db, session_id=session_id))
    await db.commit()
    for run_id in closed:
        await safe_publish_to_run(rt, str(run_id), "game_ended", {})
    return CompleteCohortResponse(cohort=cohort, warnings=warnings)


# ── Sessions ─────────────────────────────────────────────────────────────────

async def _session_out(db: AsyncSession, session: Session, cohort: Cohort | None = None) -> SessionOut:
    rows = (await db.execute(
        select(SessionInstructor, User.full_name, DeliveryRole.name)
        .join(User, User.id == SessionInstructor.user_id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(SessionInstructor.session_id == session.id)
    )).all()
    interest_count = (await db.execute(
        select(func.count())
        .select_from(InstructorInterest)
        .where(InstructorInterest.session_id == session.id)
    )).scalar_one()

    out = SessionOut.model_validate(session)
    out.instructors = [
        SessionInstructorOut(user_id=si.user_id, full_name=name, role=role_name)
        for si, name, role_name in rows
    ]
    out.target_user_ids = await staffing_service.call_target_ids(db, session.id)
    out.interested_count = interest_count

    # Session override wins; otherwise inherit the cohort's location.
    effective_id = session.location_id
    if effective_id is None:
        if cohort is None:
            cohort = await db.get(Cohort, session.cohort_id)
        effective_id = cohort.location_id if cohort else None
    if effective_id:
        location = await db.get(Location, effective_id)
        if location:
            out.effective_location_id = location.id
            out.effective_location_name = location.name

    # Same override chain for warehouse — session, then cohort, then
    # auto-resolve from the effective location if it has exactly one.
    if cohort is None:
        cohort = await db.get(Cohort, session.cohort_id)
    explicit_warehouse_id = session.warehouse_id or (cohort.warehouse_id if cohort else None)
    warehouse = await _resolve_effective_warehouse(
        db, warehouse_id=explicit_warehouse_id, location_id=effective_id
    )
    if warehouse is not None:
        out.effective_warehouse_id = warehouse.id
        out.effective_warehouse_name = warehouse.name

    materials, _ = await materials_service.resolve_for_session(db, session)
    out.materials_count = len(materials)
    kits, _ = await resolve_session_kits(db, session)
    out.kits_count = len(kits)

    return out


async def seed_cohort_sessions_from_template(
    db: AsyncSession, cohort: Cohort, new_sessions: list[Session], actor_user_id: uuid.UUID,
) -> None:
    """When sessions are added or generated for a cohort, inherit day config
    (titles, duration, checklists, and pre-session quizzes) from its variation days
    (or legacy template cohort if no variation exists)."""
    if not getattr(cohort, "inherit_default_checklists", True):
        return
    new_ids = {s.id for s in new_sessions}
    if not new_ids:
        return

    var = await var_svc.resolve_variation_for_program(db, cohort.program_id, getattr(cohort, "variation_id", None))
    v_days = await var_svc.variation_days(db, var.id) if var is not None else []

    if var is not None and not v_days:
        return

    template_days: list[ProgramVariationDay | Session] = list(v_days)
    is_legacy = False
    if var is None:
        template_cohort = await day_service.find_program_template_cohort(
            db, cohort.program_id, exclude_cohort_id=cohort.id,
        )
        if template_cohort is None:
            return
        template_days = list((await db.execute(
            select(Session).where(Session.cohort_id == template_cohort.id)
            .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
        )).scalars().all())
        is_legacy = True

    if not template_days:
        return

    all_sessions = (await db.execute(
        select(Session).where(Session.cohort_id == cohort.id)
        .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
    )).scalars().all()

    for idx, s in enumerate(all_sessions):
        if s.id not in new_ids:
            continue
        if idx >= len(template_days):
            break
        t_day = template_days[idx]
        if not s.title and t_day.title:
            s.title = t_day.title
        if s.starts_at is None and getattr(t_day, "starts_at", None) is not None:
            s.starts_at = t_day.starts_at
        if s.duration_hours is None:
            if t_day.duration_hours is not None:
                s.duration_hours = t_day.duration_hours
            elif cohort.duration_hours is not None:
                s.duration_hours = cohort.duration_hours

        src_col = DeliveryChecklistItem.session_id if is_legacy else DeliveryChecklistItem.variation_day_id
        quiz_col = PreSessionQuizAssignment.session_id if is_legacy else PreSessionQuizAssignment.variation_day_id

        existing_count = await db.scalar(
            select(func.count(DeliveryChecklistItem.id)).where(DeliveryChecklistItem.session_id == s.id)
        )
        if existing_count == 0:
            t_items = (await db.execute(
                select(DeliveryChecklistItem).where(src_col == t_day.id)
                .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
            )).scalars().all()
            for ti in t_items:
                db.add(day_service.clone_delivery_checklist_item(
                    ti, actor_user_id=actor_user_id, session_id=s.id,
                ))

        existing_quiz = (await db.execute(
            select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.session_id == s.id)
        )).scalars().first()
        if existing_quiz is None:
            t_quiz = (await db.execute(
                select(PreSessionQuizAssignment).where(quiz_col == t_day.id)
            )).scalars().first()
            if t_quiz is not None:
                db.add(PreSessionQuizAssignment(
                    id=uuid.uuid4(),
                    session_id=s.id,
                    preset_id=t_quiz.preset_id,
                ))
    await db.flush()


@router.post("/cohorts/{cohort_id}/sessions:generate", response_model=GenerateSessionsResponse)
async def generate_sessions(
    cohort_id: uuid.UUID,
    body: GenerateSessionsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    cohort = await require_cohort_manager_or_ops(db, cohort_id, current_user)
    if cohort.starts_on is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Cohort has no starts_on date to generate sessions from")
    if not body.weekdays:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="weekdays must have at least one entry")
    if any(not (0 <= w <= 6) for w in body.weekdays):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="each weekday must be between 0 (Monday) and 6 (Sunday)")
    if body.count < 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="count must be at least 1")

    created: list[Session] = []
    skipped = 0
    for weekday in body.weekdays:
        # First occurrence of this weekday on/after cohort.starts_on.
        days_ahead = (weekday - cohort.starts_on.weekday()) % 7
        first_date: date = cohort.starts_on + timedelta(days=days_ahead)

        for i in range(body.count):
            meeting_date = first_date + timedelta(weeks=i)
            existing = await db.scalar(
                select(Session.id).where(
                    Session.cohort_id == cohort_id,
                    Session.meeting_date == meeting_date,
                    Session.starts_at == body.starts_at,
                )
            )
            if existing is not None:
                skipped += 1
                continue

            session = Session(
                id=uuid.uuid4(), cohort_id=cohort_id, meeting_date=meeting_date, starts_at=body.starts_at,
            )
            db.add(session)
            try:
                async with db.begin_nested():
                    await db.flush()
            except IntegrityError:
                # Belt-and-braces against the uq_session_slot constraint —
                # the SELECT above already covers the common case.
                skipped += 1
                continue
            created.append(session)

    if created:
        await seed_cohort_sessions_from_template(db, cohort, created, current_user.id)

    await db.commit()
    return GenerateSessionsResponse(
        created=[await _session_out(db, s) for s in created], skipped=skipped,
    )


@router.get("/cohorts/{cohort_id}/sessions", response_model=list[SessionOut])
async def list_sessions(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    if not await can_read_cohort(db, cohort, current_user):
        allowed = await instructor_cohort_ids(db, user=current_user)
        if allowed is not None and cohort_id not in allowed:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    result = await db.execute(
        select(Session)
        .where(Session.cohort_id == cohort_id)
        .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
    )
    return [await _session_out(db, s, cohort) for s in result.scalars().all()]


@router.post("/cohorts/{cohort_id}/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def add_session(
    cohort_id: uuid.UUID,
    body: AddSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """A single one-off session date — for schedules that don't fit the
    weekly generator above (an irregular extra session, a make-up date)."""
    cohort = await require_cohort_manager_or_ops(db, cohort_id, current_user)
    if body.duration_hours is not None and not await can_manage_cohort_delivery(db, cohort, current_user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="Duration hours for SpacePoint-managed cohorts are managed by SpacePoint Ops.",
        )

    session = Session(
        id=uuid.uuid4(), cohort_id=cohort_id, meeting_date=body.meeting_date,
        starts_at=body.starts_at, title=body.title, material_url=body.material_url,
        duration_hours=body.duration_hours,
    )
    db.add(session)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A session already exists at this date and time")
    await seed_cohort_sessions_from_template(db, cohort, [session], current_user.id)
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session, cohort)


@router.patch("/cohorts/{cohort_id}/sessions/{session_id}", response_model=SessionOut)
async def update_session(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    body: UpdateSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    session, _cohort = await require_session_manager_or_ops(db, session_id, current_user, cohort_id=cohort_id)

    changes = body.model_dump(exclude_unset=True)
    if not is_ops_or_admin(current_user):
        changes.pop("warehouse_id", None)
        if (
            "duration_hours" in changes
            and changes["duration_hours"] != session.duration_hours
            and not await can_manage_cohort_delivery(db, _cohort, current_user)
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Duration hours for SpacePoint-managed cohorts are managed by SpacePoint Ops.",
            )
    if changes.get("location_id") and changes["location_id"] != session.location_id:
        loc = await db.get(Location, changes["location_id"])
        if loc is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Location not found")
        if not is_ops_or_admin(current_user):
            org_id = await cohort_organization_id(db, _cohort)
            if org_id is None or loc.organization_id != org_id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Location does not belong to your organization")
    if changes.get("warehouse_id") and await db.get(Warehouse, changes["warehouse_id"]) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Warehouse not found")

    for field, value in changes.items():
        setattr(session, field, value)
    try:
        async with db.begin_nested():
            await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="A session already exists at this date and time")
    await db.commit()
    await db.refresh(session)
    return await _session_out(db, session)


@router.delete("/cohorts/{cohort_id}/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Only ever deletes a session nobody was marked present or absent for —
    attendance_records.session_id cascades. Instructor assignments and any
    registration_sessions rows restricting a registration to this session do
    cascade away, which is what you want when removing a date that was
    scheduled by mistake or generated one too many times.
    """
    session, _cohort = await require_session_manager_or_ops(db, session_id, current_user, cohort_id=cohort_id)

    attendance_count = await db.scalar(
        select(func.count()).select_from(AttendanceRecord).where(AttendanceRecord.session_id == session_id)
    )
    if attendance_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=(
                f"Attendance has been recorded for {attendance_count} student(s) in this session, "
                "so it can't be deleted."
            ),
        )

    await db.delete(session)
    await db.commit()


# ── Per-session instructor assignment ───────────────────────────────────────

@router.post(
    "/cohorts/{cohort_id}/sessions/{session_id}/instructors",
    response_model=SessionInstructorOut, status_code=status.HTTP_201_CREATED,
)
async def assign_instructor(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    body: AssignInstructorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    session, cohort = await require_session_delivery_manager_or_ops(db, session_id, current_user, cohort_id=cohort_id)
    user = await db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    await assert_user_eligible_for_cohort_staffing(db, cohort, user)

    existing = await db.scalar(
        select(SessionInstructor).where(
            SessionInstructor.session_id == session_id, SessionInstructor.user_id == body.user_id,
        )
    )
    # I5-3: omitted role means the most senior one — what `role="lead"` meant
    # before roles were configurable.
    role_id = body.role_id or await lead_role_id(db)
    if role_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No delivery roles are configured")
    role = await db.get(DeliveryRole, role_id)
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Delivery role not found")

    is_new_assignment = existing is None
    if existing is not None:
        existing.role_id = role_id
    else:
        db.add(SessionInstructor(id=uuid.uuid4(), session_id=session_id, user_id=body.user_id, role_id=role_id))
    await db.flush()
    # Direct assign bypasses the open-call/interest marketplace entirely (W4).
    # I5-4: "staffed" means every opening filled; with no openings it falls
    # back to "somebody is assigned", exactly as before.
    session.staffing_status = "staffed" if await fully_staffed(db, session_id) else "open_call"

    # Direct assign used to notify nobody — only the marketplace path
    # (staffing.select_instructors) did. Same notify+email pair here so an
    # instructor finds out regardless of which path put them on the session.
    if is_new_assignment:
        cohort = await db.get(Cohort, cohort_id)
        location = await resolve_session_location_display(db, session, cohort)
        where = f" at {location['name']}" if location["name"] else ""
        if location["address"]:
            where += f", {location['address']}"
        await create_notification(
            db, body.user_id, "You've been assigned to a session",
            body=f"You're assigned ({role.name}) to a session on {session.meeting_date}{where}.",
            type="staffing_assigned",
        )
        await safe_enqueue(arq_redis, "send_assignment_email", str(session_id), str(body.user_id))

    await db.commit()
    return SessionInstructorOut(user_id=user.id, full_name=user.full_name, role=role.name)


@router.delete("/cohorts/{cohort_id}/sessions/{session_id}/instructors/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_instructor(
    cohort_id: uuid.UUID,
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    session, _cohort = await require_session_delivery_manager_or_ops(db, session_id, current_user, cohort_id=cohort_id)

    assignment = await db.scalar(
        select(SessionInstructor).where(
            SessionInstructor.session_id == session_id, SessionInstructor.user_id == user_id,
        )
    )
    if assignment is not None:
        await db.delete(assignment)
        await db.flush()
        remaining = await db.scalar(
            select(func.count()).select_from(SessionInstructor).where(SessionInstructor.session_id == session_id)
        )
        # Only auto-revert a direct assignment's implicit "staffed" — never
        # touches open_call (that's the marketplace's own explicit reopen()).
        if remaining == 0 and session.staffing_status == "staffed":
            session.staffing_status = "unstaffed"
        # S4-2 spec: "on removal -> notify" (in-app only, no email — unlike
        # selection, being taken off a session isn't a calendar event).
        await create_notification(
            db, user_id, "Removed from a session",
            body=f"You've been removed from the session on {session.meeting_date}.",
            type="staffing_removed",
        )
        await db.commit()


# ── Bulk session actions (2026-08-01) ───────────────────────────────────────
# A cohort with 100 sessions shouldn't mean 100 taps for the common cases:
# the same instructor onto several sessions, or opening several calls at
# once. Both loop the exact same per-session logic used above/in the
# staffing service — partial failure doesn't roll back the rest of the batch,
# it's reported back per session instead.

@router.post("/cohorts/{cohort_id}/sessions/bulk-assign-instructor", response_model=BulkActionResult)
async def bulk_assign_instructor(
    cohort_id: uuid.UUID,
    body: BulkAssignInstructorRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    cohort = await require_cohort_delivery_manager_or_ops(db, cohort_id, current_user)
    user = await db.get(User, body.user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="User not found")
    await assert_user_eligible_for_cohort_staffing(db, cohort, user)
    role_id = body.role_id or await lead_role_id(db)
    if role_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="No delivery roles are configured")
    if await db.get(DeliveryRole, role_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Delivery role not found")

    succeeded: list[uuid.UUID] = []
    failed: list[BulkActionError] = []
    for session_id in dict.fromkeys(body.session_ids):  # de-dupe, keep order
        session = await db.get(Session, session_id)
        if session is None or session.cohort_id != cohort_id:
            failed.append(BulkActionError(session_id=session_id, detail="Session not found in this cohort"))
            continue

        existing = await db.scalar(
            select(SessionInstructor).where(
                SessionInstructor.session_id == session_id, SessionInstructor.user_id == body.user_id,
            )
        )
        if existing is not None:
            existing.role_id = role_id
        else:
            db.add(SessionInstructor(id=uuid.uuid4(), session_id=session_id, user_id=body.user_id, role_id=role_id))
        await db.flush()
        session.staffing_status = "staffed" if await fully_staffed(db, session_id) else "open_call"
        succeeded.append(session_id)

    await db.commit()
    return BulkActionResult(succeeded=succeeded, failed=failed)


@router.post("/cohorts/{cohort_id}/sessions/bulk-open-call", response_model=BulkActionResult)
async def bulk_open_call(
    cohort_id: uuid.UUID,
    body: BulkOpenCallRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Same targeting/role-scoping a single "Target Instructors…" call takes,
    applied to every listed session — the ask that "Open Call (All
    Instructors)" and the per-session targeted modal don't cover: a chosen
    subset of sessions, optionally restricted to specific instructors."""
    succeeded: list[uuid.UUID] = []
    failed: list[BulkActionError] = []
    for session_id in dict.fromkeys(body.session_ids):
        session = await db.get(Session, session_id)
        if session is None or session.cohort_id != cohort_id:
            failed.append(BulkActionError(session_id=session_id, detail="Session not found in this cohort"))
            continue
        try:
            await staffing_service.open_call(
                db, session_id, body.target_user_ids, body.role_ids, actor_user_id=current_user.id,
            )
            succeeded.append(session_id)
        except HTTPException as e:
            failed.append(BulkActionError(session_id=session_id, detail=str(e.detail)))

    await db.commit()
    return BulkActionResult(succeeded=succeeded, failed=failed)


# ── Session reports (W5 S5-2) ────────────────────────────────────────────────

@router.post("/cohorts/{cohort_id}/reports", response_model=SessionReportOut, status_code=status.HTTP_201_CREATED)
async def upload_session_report(
    cohort_id: uuid.UUID,
    file: UploadFile = File(...),
    session_id: uuid.UUID | None = Form(None),
    notes: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Assigned instructor (if session_id given) or ops/admin. A cohort-level
    report (no session_id) is ops/admin only — there's no per-user
    assignment concept above the session level."""
    data = await file.read()
    report = await reports_service.upload_report(
        db, cohort_id, session_id, data, file.filename or "report",
        file.content_type or "application/octet-stream", notes, current_user,
    )
    await db.commit()
    file_url = await reports_service.resolve_report_url(report)
    return SessionReportOut(
        id=report.id, cohort_id=report.cohort_id, session_id=report.session_id,
        uploaded_by=report.uploaded_by, uploaded_by_name=current_user.full_name,
        file_url=file_url, filename=reports_service.display_filename(report.file_ref),
        notes=report.notes, created_at=report.created_at,
    )


@router.get("/cohorts/{cohort_id}/reports", response_model=list[SessionReportOut])
async def list_cohort_reports(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    await require_cohort_read_or_ops(db, cohort_id, current_user)
    rows = await reports_service.list_reports(db, cohort_id)
    return [
        SessionReportOut(
            id=report.id, cohort_id=report.cohort_id, session_id=report.session_id,
            uploaded_by=report.uploaded_by, uploaded_by_name=uploader_name,
            file_url=await reports_service.resolve_report_url(report),
            filename=reports_service.display_filename(report.file_ref),
            notes=report.notes, created_at=report.created_at,
        )
        for report, uploader_name in rows
    ]


# ── Registrations ────────────────────────────────────────────────────────────

@router.get("/cohorts/{cohort_id}/registrations", response_model=list[RegistrationOut])
async def list_registrations(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    cohort = await require_cohort_read_or_ops(db, cohort_id, current_user)

    Student = aliased(Contact)
    Guardian = aliased(Contact)
    StudentOrg = aliased(Organization)

    rows = (await db.execute(
        select(Registration, Student, Guardian, StudentOrg)
        .join(Student, Student.id == Registration.contact_id)
        .outerjoin(Guardian, Guardian.id == Registration.payer_contact_id)
        .outerjoin(StudentOrg, StudentOrg.id == Student.organization_id)
        .where(Registration.cohort_id == cohort_id)
        .order_by(Registration.created_at.desc())
    )).all()

    cohort_sessions = (await db.execute(
        select(Session)
        .where(Session.cohort_id == cohort_id)
        .order_by(Session.meeting_date, Session.starts_at)
    )).scalars().all()
    total_sessions_count = len(cohort_sessions)

    registration_ids = [reg.id for reg, _, _, _ in rows]
    checked_in_ids: set[uuid.UUID] = set()
    certificate_urls: dict[uuid.UUID, str] = {}
    certified_ids: set[uuid.UUID] = set()
    att_by_reg: dict[uuid.UUID, dict[uuid.UUID, AttendanceRecord]] = {}

    # last_login_at per registrant (2026-09-16) — same contact_id-first,
    # email-fallback account resolution get_or_create_student_account and
    # services/lms/students.py::_registered_cohort_users both use, so
    # "linked account" here means the same thing it does everywhere else.
    student_contact_ids = [student.id for _, student, _, _ in rows]
    last_login_by_contact: dict[uuid.UUID, datetime | None] = {}
    user_id_by_contact: dict[uuid.UUID, uuid.UUID] = {}
    card_id_by_contact: dict[uuid.UUID, str | None] = {}
    if student_contact_ids:
        linked_users = (await db.execute(
            select(User)
            .where(User.contact_id.in_(student_contact_ids))
        )).scalars().all()
        for u in linked_users:
            if u.contact_id is not None:
                last_login_by_contact[u.contact_id] = u.last_login_at
                user_id_by_contact[u.contact_id] = u.id
                card_id_by_contact[u.contact_id] = (
                    format_card_id(u.card_number, u.role_values) if u.card_number is not None else None
                )
        resolved_contact_ids = set(last_login_by_contact.keys())

        missing_emails = {
            normalize_user_email(student.email) for _, student, _, _ in rows
            if student.id not in resolved_contact_ids and student.email
            and normalize_user_email(student.email)
        }
        if missing_emails:
            by_email = {
                normalize_user_email(u.email): (
                    u.id,
                    u.last_login_at,
                    format_card_id(u.card_number, u.role_values) if u.card_number is not None else None,
                )
                for u in (await db.execute(
                    select(User).where(func.lower(User.email).in_(missing_emails))
                )).scalars().all() if u.email
            }
            for _, student, _, _ in rows:
                key = normalize_user_email(student.email) if student.email else ""
                if student.id not in resolved_contact_ids and key in by_email:
                    uid, last_login, cid = by_email[key]
                    last_login_by_contact[student.id] = last_login
                    user_id_by_contact[student.id] = uid
                    card_id_by_contact[student.id] = cid

    if registration_ids:
        att_records = (await db.execute(
            select(AttendanceRecord)
            .where(AttendanceRecord.registration_id.in_(registration_ids))
        )).scalars().all()

        for rec in att_records:
            checked_in_ids.add(rec.registration_id)
            if rec.registration_id not in att_by_reg:
                att_by_reg[rec.registration_id] = {}
            att_by_reg[rec.registration_id][rec.session_id] = rec

        certs = (await db.execute(
            select(Certificate).where(Certificate.registration_id.in_(registration_ids))
        )).scalars().all()
        for cert in certs:
            certified_ids.add(cert.registration_id)
            # resolve_url already prefers a fresh signed URL from (bucket, path)
            # and falls back to a stored file_url — guarding on bucket/path here
            # defeated that fallback, hiding the URL on any row that only has
            # file_url. Student completion certs have neither (emailed, never
            # stored), so they correctly stay None while still being reported
            # as issued via certified_ids.
            url = await storage.resolve_url(cert.bucket, cert.file_path, cert.file_url)
            if url:
                certificate_urls[cert.registration_id] = url

    latest_consents = await get_latest_consents_for_registrations(db, registration_ids)

    result_registrations = []
    for reg, student, guardian, student_org in rows:
        reg_att_dict = att_by_reg.get(reg.id, {})
        att_list = []
        attended_count = 0
        for s in cohort_sessions:
            rec = reg_att_dict.get(s.id)
            status_val = rec.att_status if rec else "unrecorded"
            # Attendance is present|absent; this used to also count "late",
            # which disagreed with the certificate rule's present-only count.
            if status_val == "present":
                attended_count += 1
            att_list.append(
                RegistrationAttendanceOut(
                    session_id=s.id,
                    meeting_date=s.meeting_date,
                    session_title=s.title,
                    att_status=status_val,
                    recorded_at=rec.recorded_at if rec else None,
                )
            )

        consent = latest_consents.get(reg.id)
        media_consent_status = consent.consent_choice if consent else "pending"

        result_registrations.append(
            RegistrationOut(
                id=reg.id,
                contact_id=reg.contact_id,
                student_name=student.full_name,
                student_phone=student.primary_phone_e164,
                student_email=student.email,
                student_date_of_birth=student.date_of_birth,
                student_grade=student.grade,
                student_gender=student.gender,
                student_organization_name=student_org.name_latin if student_org is not None else None,
                payer_contact_id=reg.payer_contact_id,
                guardian_name=consent.parent_name if (consent and consent.parent_name) else (guardian.full_name if guardian is not None else None),
                guardian_phone=consent.parent_phone if (consent and consent.parent_phone) else (guardian.primary_phone_e164 if guardian is not None else None),
                payment_status=reg.payment_status,
                price_charged=reg.price_charged,
                status=reg.status,
                registered_via=reg.registered_via,
                is_repeat=reg.is_repeat,
                ticket_sent=reg.ticket_sent_at is not None,
                onboarding_sent=reg.onboarding_sent_at is not None,
                checked_in=reg.id in checked_in_ids,
                certificate_issued=reg.id in certified_ids,
                certificate_url=certificate_urls.get(reg.id),
                attended_sessions_count=attended_count,
                total_cohort_sessions_count=total_sessions_count,
                attendance_records=att_list,
                created_at=reg.created_at,
                last_login_at=last_login_by_contact.get(reg.contact_id),
                card_id=card_id_by_contact.get(reg.contact_id),
                lms_user_id=user_id_by_contact.get(reg.contact_id),
                media_consent_status=media_consent_status,
                media_consent_id=consent.id if consent else None,
                media_consent_parent_name=consent.parent_name if consent else (guardian.full_name if guardian else None),
                media_consent_parent_phone=consent.parent_phone if consent else (guardian.primary_phone_e164 if guardian else None),
                media_consent_parent_email=consent.parent_email if consent else (guardian.email if guardian else None),
                media_consent_relationship=consent.relationship if consent else None,
                media_consent_signed_date=consent.date_of_signing if consent else None,
                media_consent_grants=consent.permission_grants if (consent and consent.permission_grants) else [],
                media_consent_notes=consent.notes if consent else None,
            )
        )
    return result_registrations


# ── Manual (desk) registration ───────────────────────────────────────────────

@router.post("/cohorts/{cohort_id}/registrations", status_code=status.HTTP_201_CREATED)
async def desk_register(
    cohort_id: uuid.UUID,
    body: DeskRegistrationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    cohort = await require_cohort_manager_or_ops(db, cohort_id, current_user)
    org_id = await cohort_organization_id(db, cohort)
    if org_id is not None and not is_ops_or_admin(current_user):
        org = await db.get(Organization, org_id)
        if org is not None:
            if not org.is_approved:
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail="Your organization account is under review. Enrollment is locked until approved.",
                )
            if is_partner_managed(cohort) and org.max_students_per_cohort is not None:
                active_count = await db.scalar(
                    select(func.count(Registration.id)).where(
                        Registration.cohort_id == cohort.id,
                        Registration.status != "cancelled",
                    )
                ) or 0
                if active_count >= org.max_students_per_cohort:
                    raise HTTPException(
                        status.HTTP_400_BAD_REQUEST,
                        detail=f"Your organization limit is {org.max_students_per_cohort} students per cohort.",
                    )

    student, _ = await resolve_or_create_contact(
        db,
        full_name=body.student_name,
        phone=body.phone,
        email=body.email,
        contact_roles=["student"],
        city=body.city,
        role_event_source="desk",
        date_of_birth=body.date_of_birth,
        grade=body.grade,
        gender=body.gender,
        organization_id=org_id if (org_id is not None and not body.organization_name) else None,
        organization_name=body.organization_name,
    )

    payer_contact_id = None
    if body.parent_name and body.parent_phone:
        guardian, _ = await resolve_or_create_contact(
            db,
            full_name=body.parent_name,
            phone=body.parent_phone,
            email=body.parent_email,
            contact_roles=["parent_guardian"],
            role_event_source="desk",
        )
        payer_contact_id = guardian.id
        await _ensure_guardian_relationship(db, student_id=student.id, guardian_id=guardian.id)

    registration = await register(
        db,
        contact_id=student.id,
        cohort_id=cohort.id,
        payer_contact_id=payer_contact_id,
        registered_via="desk",
        session_ids=body.session_ids,
    )

    # LM1-7 / D4: default-checked — creates (or links) a student account and
    # enrolls in the program's curriculum. Covers both a fresh registration
    # and a reinstated one (enroll()'s own idempotency reactivates in place).
    # Never raises — an LMS-side hiccup must not break registration.
    await sync_registration_lms(
        db, registration=registration, cohort=cohort, create_account=body.create_lms_account,
        send_welcome_email=body.send_welcome_email,
    )

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("desk_register failed to commit for cohort %s: %s", cohort_id, exc)
        msg = str(exc)
        if "unique constraint" in msg.lower() or "uniqueviolation" in msg.lower():
            if "card_number" in msg.lower():
                detail = "An ID card number conflict occurred during registration. Please retry."
            elif "email" in msg.lower():
                detail = "An account with this email already exists and could not be linked."
            else:
                detail = f"Database uniqueness conflict during registration: {msg}"
        else:
            detail = f"Could not complete registration: {msg}"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)

    # Ticket email runs on the ARQ queue, not synchronously — same pattern as
    # the public registration endpoint (routers/sessions/public.py). Desk
    # staff can opt out entirely (e.g. printing the ticket directly instead).
    if body.send_ticket_email:
        await safe_enqueue(arq_redis, "send_ticket_email", str(registration.id))

    return {
        "id": str(registration.id),
        "contact_id": str(student.id),
        "payer_contact_id": str(payer_contact_id) if payer_contact_id else None,
        "status": registration.status,
    }


async def _ensure_guardian_relationship(db: AsyncSession, *, student_id: uuid.UUID, guardian_id: uuid.UUID) -> None:
    """Copied verbatim from routers/sessions/public.py — see that module for
    the canonical version; do not let this drift from it."""
    result = await db.execute(
        select(ContactRelationship).where(
            ContactRelationship.contact_id == guardian_id,
            ContactRelationship.related_contact_id == student_id,
            ContactRelationship.relation == "guardian_of",
        )
    )
    if result.scalars().first() is not None:
        return
    db.add(ContactRelationship(
        id=uuid.uuid4(), contact_id=guardian_id, related_contact_id=student_id, relation="guardian_of",
    ))
    await db.flush()


# ── Registration actions ─────────────────────────────────────────────────────

@router.post("/registrations/{registration_id}/resend-ticket")
async def resend_ticket(
    registration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
    arq_redis: ArqRedis | None = Depends(get_arq_redis),
):
    registration, _cohort = await require_registration_manager_or_ops(db, registration_id, current_user)

    # force=True: this is the one path where re-sending an already-sent ticket
    # is the intent, so it deliberately bypasses issue_ticket's idempotency guard.
    status_ = await safe_enqueue(
        arq_redis, "send_ticket_email", str(registration.id), force=True
    )
    return {"status": status_}


@router.post("/registrations/{registration_id}/resend-onboarding-email")
async def resend_onboarding_email(
    registration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    registration, cohort = await require_registration_manager_or_ops(db, registration_id, current_user)
    contact = await db.get(Contact, registration.contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No LMS account linked to this registration")
    user = await resolve_user_for_contact(db, contact)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No LMS account linked to this registration")

    # Synchronous, not queued — same as the automatic send this mirrors
    # (sync_registration_lms), unlike the ticket email which is worker-only.
    sent = await send_registration_onboarding_email(db, user=user, registration=registration, cohort=cohort)
    await db.commit()
    return {"sent": sent}


@router.post("/registrations/{registration_id}/set-password-link")
async def get_set_password_link(
    registration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Hands ops the raw set-password link instead of emailing it — for
    students who don't check the inbox that email went to, ops copies this
    and sends it themselves over WhatsApp/SMS. Same token/link
    `resend-onboarding-email` sends by mail (build_set_password_link)."""
    registration, _cohort = await require_registration_manager_or_ops(db, registration_id, current_user)
    contact = await db.get(Contact, registration.contact_id)
    if contact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No LMS account linked to this registration")
    user = await resolve_user_for_contact(db, contact)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No LMS account linked to this registration")

    return {"link": build_set_password_link(user)}


@router.post("/registrations/{registration_id}/cancel")
async def cancel_registration(
    registration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    registration, _cohort = await require_registration_manager_or_ops(db, registration_id, current_user)

    registration.status = "cancelled"
    # LM1-7 / D4: a cancelled registration takes its LMS enrollments with it
    # (inactive, not deleted — progress survives in case of reinstatement).
    await deactivate_registration_enrollments(db, registration.id)
    await db.commit()
    return {"id": str(registration.id), "status": registration.status}


@router.delete("/registrations/{registration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_registration(
    registration_id: uuid.UUID,
    delete_contact: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Erases a sign-up — attendance and any certificate for it go too.

    Cancel (above) is the safe option: it keeps the row and the history, and
    frees the seat either way since cancelled registrations don't count against
    capacity. Delete is the destructive one, for rows that shouldn't exist —
    a wrong cohort, a duplicate, a typo — and it does not hold back once
    attendance has been taken (operator decision, 2026-07-26). Certificates are
    removed explicitly because certificates.registration_id is SET NULL, so
    they'd otherwise survive as orphans pointing at nobody.

    `delete_contact=true` additionally removes the person from Contacts. Two
    things are refused rather than done quietly, because contacts.id cascades
    to nine tables and a contact is shared across every cohort:

      · a contact linked to a staff user account — deleting the person record
        behind a real login is never what's meant here
      · a contact with registrations in other cohorts — those, and their
        attendance and certificates, would vanish with no warning

    In both cases the operator is told what's attached; deleting the other
    registrations first still gets them a clean removal.
    """
    registration, _cohort = await require_registration_manager_or_ops(db, registration_id, current_user)
    if not is_ops_or_admin(current_user):
        delete_contact = False

    contact_id = registration.contact_id

    if delete_contact:
        linked_users = (await db.execute(
            select(User).where(User.contact_id == contact_id)
        )).scalars().all()

        has_staff_account = any(
            any(r != UserRole.student and r != "student" for r in (u.roles or []))
            for u in linked_users
        )
        if has_staff_account:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    "This person has a staff account on the platform, so their contact can't "
                    "be deleted. The registration alone can still be removed."
                ),
            )

        other_registrations = await db.scalar(
            select(func.count()).select_from(Registration).where(
                Registration.contact_id == contact_id, Registration.id != registration_id,
            )
        )
        if other_registrations:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail=(
                    f"This person is registered in {other_registrations} other cohort(s). "
                    "Deleting their contact would erase those registrations and their "
                    "attendance too. Remove those registrations first, or delete this one "
                    "without deleting the contact."
                ),
            )

    await db.execute(
        sa_delete(Certificate).where(Certificate.registration_id == registration_id)
    )
    await db.delete(registration)
    await db.flush()

    if delete_contact:
        student_users = (await db.execute(
            select(User).where(User.contact_id == contact_id)
        )).scalars().all()
        for u in student_users:
            await db.delete(u)
        await db.flush()

        contact = await db.get(Contact, contact_id)
        if contact is not None:
            await db.delete(contact)

    await db.commit()


@router.post("/registrations/{registration_id}/certificate")
async def give_certificate(
    registration_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """Manual override (operator request 2026-07-25): ops can hand a
    certificate to a student who didn't meet the program's completion rule
    — it's just never auto-sent for them. Idempotent, same as the automatic
    path in complete_cohort."""
    await require_registration_manager_or_ops(db, registration_id, current_user)
    certificate = await delivery.issue_certificate_override(db, registration_id, current_user.id)
    await db.commit()
    # Student completion certs are emailed directly — no file stored, no URL to return.
    return {"id": str(registration_id), "status": "completed", "certificate_id": str(certificate.id)}


@router.get("/cohorts/{cohort_id}/certificates/download")
async def download_cohort_certificates(
    cohort_id: uuid.UUID,
    theme: str = Query("dark"),
    template_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """One PDF, one page per *registered* student in this cohort — for
    printing at the workshop, not gated on completion/issuance status (every
    registrant gets a page, same as complete_cohort's auto-issue would
    eventually give them, just generated up front here instead). Cancelled
    registrations are excluded, same convention as list_cohorts' counts.
    Generated fresh each time, nothing persisted or emailed — this is a
    print run, not the student_completion issuance flow in delivery.py.
    `theme` or `template_id` picks the layout and background template."""
    cohort = await require_cohort_read_or_ops(db, cohort_id, current_user)
    program = await db.get(Program, cohort.program_id)

    rows = (await db.execute(
        select(Contact.full_name)
        .join(Registration, Registration.contact_id == Contact.id)
        .where(Registration.cohort_id == cohort_id, Registration.status != "cancelled")
        .order_by(Contact.full_name)
    )).scalars().all()
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="No registered students in this cohort yet")

    from app.services.competitions.certificates import _resolve_certificate_template
    layout = await _resolve_certificate_template(db, program=program, cohort=cohort, template_id=template_id, theme=theme)

    template = (await db.execute(
        select(DocumentTemplate).where(DocumentTemplate.key == "student_completion")
    )).scalars().first()
    location = await resolve_session_location_display(db, None, cohort)
    if layout.get("is_custom"):
        template_body = layout.get("body_text_template") or ""
    else:
        template_body = layout.get("body_text_template") or (template.body_text if template else STUDENT_COMPLETION_FALLBACK_BODY)
    program_name = program.name if program else ""
    cohort_title = cohort.name if cohort and cohort.name else ""
    body_text = expand_certificate_body_template(
        template_body,
        program_name=program_name,
        cohort_name=cohort_title,
        dates=format_cohort_dates(cohort),
        starts_on=cohort.starts_on,
        ends_on=cohort.ends_on,
        location=location["name"],
    )

    def _render(name: str, body: str) -> bytes:
        return generate_completion_certificate_pdf(
            recipient_name=name,
            body_text_template=body,
            background_bytes=layout["background_bytes"],
            theme=layout["theme"],
            name_font_size=layout["name_font_size"],
            name_y=layout["name_y"],
            name_color=layout["name_color"],
            body_font_size=layout["body_font_size"],
            body_y=layout["body_y"],
            body_color=layout["body_color"],
            body_max_width=layout["body_max_width"],
            body_alignment=layout["body_alignment"],
            show_signature=layout["show_signature"],
            signature_bytes=layout["signature_bytes"],
            signature_x=layout["signature_x"],
            signature_y=layout["signature_y"],
            signature_width=layout["signature_width"],
            signature_height=layout["signature_height"],
            signatory_name=layout.get("signatory_name"),
            signatory_title=layout.get("signatory_title"),
        )

    pages = [await asyncio.to_thread(_render, full_name, body_text) for full_name in rows]

    merged = await asyncio.to_thread(merge_certificate_pdfs, pages)
    safe_name = "".join(c for c in cohort.name if c.isalnum() or c in " -_").strip().replace(" ", "_")
    return Response(
        content=merged, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="certificates_{safe_name or cohort_id}.pdf"'},
    )


@router.post("/registrations/{registration_id}/confirm-payment")
async def confirm_payment(
    registration_id: uuid.UUID,
    body: ConfirmPaymentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    registration, _cohort = await require_registration_manager_or_ops(db, registration_id, current_user)
    if not is_ops_or_admin(current_user):
        delete_contact = False

    registration.price_charged = body.amount
    registration.payment_status = body.status
    await db.commit()
    return {
        "id": str(registration.id),
        "payment_status": registration.payment_status,
        "price_charged": str(registration.price_charged),
    }


@router.get("/{session_id}/history")
async def session_history(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_session_delivery),
):
    """3-phase session audit trail: pre-session, during-session, post-session."""
    session, _cohort = await require_session_read_or_ops(db, session_id, current_user)

    instructors_rows = (await db.execute(
        select(SessionInstructor, User, DeliveryRole)
        .join(User, User.id == SessionInstructor.user_id)
        .join(DeliveryRole, DeliveryRole.id == SessionInstructor.role_id)
        .where(SessionInstructor.session_id == session_id)
    )).all()
    instructor_roles = {u.id: (u.full_name, r.name) for _, u, r in instructors_rows}

    movements = (await db.execute(
        select(Movement)
        .where(Movement.session_id == session_id)
        .order_by(Movement.created_at.asc())
    )).scalars().all()

    loc_ids = {m.from_location_id for m in movements if m.from_location_id} | {m.to_location_id for m in movements if m.to_location_id}
    wh_ids = {m.from_warehouse_id for m in movements if m.from_warehouse_id} | {m.to_warehouse_id for m in movements if m.to_warehouse_id}
    usr_ids = {m.from_user_id for m in movements if m.from_user_id} | {m.to_user_id for m in movements if m.to_user_id} | {m.created_by for m in movements if m.created_by}
    item_ids = {m.item_id for m in movements if m.item_id}
    kit_ids = {m.kit_id for m in movements if m.kit_id}

    locations = {l.id: l.name for l in (await db.execute(select(Location).where(Location.id.in_(loc_ids)))).scalars().all()} if loc_ids else {}
    warehouses = {w.id: w.name for w in (await db.execute(select(Warehouse).where(Warehouse.id.in_(wh_ids)))).scalars().all()} if wh_ids else {}
    users = {u.id: u.full_name for u in (await db.execute(select(User).where(User.id.in_(usr_ids)))).scalars().all()} if usr_ids else {}
    items = {i.id: i.name for i in (await db.execute(select(Item).where(Item.id.in_(item_ids)))).scalars().all()} if item_ids else {}
    kits = {k.id: k.label for k in (await db.execute(select(Kit).where(Kit.id.in_(kit_ids)))).scalars().all()} if kit_ids else {}

    pre_movements = []
    post_movements = []
    for m in movements:
        target_uid = m.from_user_id or m.to_user_id or m.created_by
        inst_name, inst_role = instructor_roles.get(
            target_uid, (users.get(target_uid, "Instructor"), "Instructor")
        )
        entry = {
            "id": str(m.id),
            "reason": m.reason,
            "subject": kits.get(m.kit_id) if m.kit_id else (f"{items.get(m.item_id)} (x{m.qty})" if m.item_id else "Equipment"),
            "is_kit": bool(m.kit_id),
            "qty": m.qty,
            "from_warehouse_name": warehouses.get(m.from_warehouse_id),
            "to_warehouse_name": warehouses.get(m.to_warehouse_id),
            "from_location_name": locations.get(m.from_location_id),
            "to_location_name": locations.get(m.to_location_id),
            "actor_name": inst_name,
            "actor_role": inst_role,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "due_back_on": m.due_back_on.isoformat() if m.due_back_on else None,
            "note": m.note,
        }
        if m.reason == "issue":
            pre_movements.append(entry)
        elif m.reason in ("return", "adjust", "writeoff"):
            post_movements.append(entry)

    kit_checks = (await db.execute(
        select(KitCheck).where(KitCheck.session_id == session_id).order_by(KitCheck.created_at.asc())
    )).scalars().all()

    check_user_ids = {kc.checked_by for kc in kit_checks if kc.checked_by}
    check_users = {u.id: u.full_name for u in (await db.execute(select(User).where(User.id.in_(check_user_ids)))).scalars().all()} if check_user_ids else {}

    pre_checks = []
    post_checks = []
    for kc in kit_checks:
        c_name, c_role = instructor_roles.get(kc.checked_by, (check_users.get(kc.checked_by, "Instructor"), "Instructor"))
        kit_label = kits.get(kc.kit_id, "Kit")
        check_data = {
            "id": str(kc.id),
            "kit_id": str(kc.kit_id),
            "kit_label": kit_label,
            "phase": kc.phase,
            "skipped": kc.skipped,
            "actor_name": c_name,
            "actor_role": c_role,
            "counts": kc.counts,
            "missing": kc.missing,
            "note": kc.note,
            "created_at": kc.created_at.isoformat() if kc.created_at else None,
        }
        if kc.phase == "pre":
            pre_checks.append(check_data)
        else:
            post_checks.append(check_data)

    att_records = (await db.execute(
        select(AttendanceRecord, Registration, Contact)
        .join(Registration, Registration.id == AttendanceRecord.registration_id)
        .join(Contact, Contact.id == Registration.contact_id)
        .where(AttendanceRecord.session_id == session_id)
    )).all()

    att_summary = {"present": 0, "absent": 0, "late": 0, "excused": 0, "total": len(att_records), "records": []}
    for ar, reg, contact in att_records:
        status_val = ar.att_status
        if status_val in att_summary:
            att_summary[status_val] += 1
        att_summary["records"].append({
            "registration_id": str(reg.id),
            "student_name": contact.full_name,
            "status": status_val,
            "marked_at": ar.recorded_at.isoformat() if ar.recorded_at else None,
        })

    reports = (await db.execute(
        select(SessionReport).where(SessionReport.session_id == session_id).order_by(SessionReport.created_at.desc())
    )).scalars().all()
    report_user_ids = {r.uploaded_by for r in reports if r.uploaded_by}
    report_users = {u.id: u.full_name for u in (await db.execute(select(User).where(User.id.in_(report_user_ids)))).scalars().all()} if report_user_ids else {}

    reports_data = []
    for r in reports:
        u_name, u_role = instructor_roles.get(r.uploaded_by, (report_users.get(r.uploaded_by, "Instructor"), "Instructor"))
        url = await storage.resolve_url("reports", r.file_ref)
        reports_data.append({
            "id": str(r.id),
            "file_url": url,
            "notes": r.notes,
            "actor_name": u_name,
            "actor_role": u_role,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    addons = await openings_svc.addons_for_session(db, session_id)

    return {
        "session_id": str(session_id),
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "completed_at": session.completed_at.isoformat() if session.completed_at else None,
        "notes": session.notes,
        "pre_session": {
            "movements": pre_movements,
            "kit_checks": pre_checks,
        },
        "during_session": {
            "attendance": att_summary,
        },
        "post_session": {
            "movements": post_movements,
            "kit_checks": post_checks,
            "reports": reports_data,
            "addons": addons,
        },
    }


# ── Cohort Media Consent (2026-09-27) ─────────────────────────────────────────

@router.post("/cohorts/{cohort_id}/media-consent/webhook")
async def media_consent_webhook(
    cohort_id: uuid.UUID,
    payload: MediaConsentWebhookRequest,
    db: AsyncSession = Depends(get_db),
):
    """Public webhook for Google Forms / Google Apps Script ingestion.
    Matches student by email first, phone second (name does NOT match).
    Updates guardian info on student if matched.
    """
    try:
        consent = await ingest_media_consent_webhook(db, cohort_id=cohort_id, payload=payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(e))

    return {
        "status": "success",
        "id": str(consent.id),
        "cohort_id": str(consent.cohort_id),
        "registration_id": str(consent.registration_id) if consent.registration_id else None,
        "matched": consent.match_status == "matched",
        "match_status": consent.match_status,
        "match_method": consent.match_method,
        "consent_choice": consent.consent_choice,
    }


@router.get("/cohorts/{cohort_id}/media-consent", response_model=CohortMediaConsentSummaryOut)
async def list_cohort_media_consents(
    cohort_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Returns summary stats and all media consent records for the cohort."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return await get_cohort_consents_summary(db, cohort_id)


@router.post("/cohorts/{cohort_id}/media-consent/manual-override", response_model=CohortMediaConsentOut)
async def manual_override_consent(
    cohort_id: uuid.UUID,
    body: MediaConsentManualOverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Manually update or set a student's media consent state (e.g. paper form, verbal, WhatsApp)."""
    try:
        consent = await manual_override_media_consent(db, cohort_id=cohort_id, req=body)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    out = CohortMediaConsentOut.model_validate(consent)
    if consent.registration_id:
        reg = await db.get(Registration, consent.registration_id)
        if reg:
            student = await db.get(Contact, reg.contact_id)
            if student:
                out.matched_student_name = student.full_name
    return out


@router.post("/cohorts/{cohort_id}/media-consent/{consent_id}/match", response_model=CohortMediaConsentOut)
async def manual_match_consent(
    cohort_id: uuid.UUID,
    consent_id: uuid.UUID,
    body: MediaConsentManualMatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_operations),
):
    """Manually link an unmatched consent form submission to a student registration."""
    try:
        consent = await manual_link_media_consent(
            db, cohort_id=cohort_id, consent_id=consent_id, registration_id=body.registration_id
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    out = CohortMediaConsentOut.model_validate(consent)
    reg = await db.get(Registration, body.registration_id)
    if reg:
        student = await db.get(Contact, reg.contact_id)
        if student:
            out.matched_student_name = student.full_name
    return out
