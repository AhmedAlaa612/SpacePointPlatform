"""Shared helper to seed a brand-new Cohort from its Program / ProgramVariation defaults.

Used by both `POST /sessions/cohorts` (Ops) and `POST /organization/cohorts`
(Partner Orgs) so Mode A/B cohorts inherit days, delivery checklists, role
openings, pre-session quizzes, and LMS overrides identically while keeping
Mode A completely isolated from SpacePoint AED pay rates and Assessment Gates.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.lms.program import LmsProgram, LmsProgramCohortOverride
from app.models.sessions.checklist import DeliveryChecklistItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.pre_session_quiz import PreSessionQuizAssignment
from app.models.sessions.program import Program
from app.models.sessions.program_variation import ProgramVariation
from app.models.sessions.session import Session
from app.services.sessions import day as day_service
from app.services.sessions import openings as openings_svc
from app.services.sessions import variations as var_svc


async def seed_cohort_from_program(
    db: AsyncSession,
    *,
    cohort: Cohort,
    program: Program,
    selected_var: ProgramVariation | None,
    apply_defaults: bool,
    eff_scalars: dict[str, Any],
    import_default_checklists: bool,
    actor_user_id: uuid.UUID,
    checklist_source_program_id: uuid.UUID | None = None,
    checklist_source_variation_id: uuid.UUID | None = None,
    ensure_lms_override: bool = False,
) -> None:
    """Populate openings, assessments, quizzes, checklists, sessions, and LMS override."""
    is_spacepoint_mode = (getattr(cohort, "management_mode", "spacepoint") or "spacepoint") == "spacepoint"

    if apply_defaults:
        await openings_svc.copy_program_openings_to_cohort(
            db,
            program_id=program.id,
            variation_id=cohort.variation_id,
            cohort_id=cohort.id,
            actor_user_id=actor_user_id,
            include_rates=is_spacepoint_mode,
        )
        if is_spacepoint_mode and eff_scalars.get("default_assessment_config_id") is not None:
            db.add(AssessmentCohortAssignment(
                id=uuid.uuid4(),
                cohort_id=cohort.id,
                config_id=eff_scalars["default_assessment_config_id"],
                assigned_by=actor_user_id,
            ))

    prog_or_var_quiz = None
    if apply_defaults:
        if cohort.variation_id is not None:
            prog_or_var_quiz = (
                await db.execute(
                    select(PreSessionQuizAssignment).where(
                        PreSessionQuizAssignment.variation_id == cohort.variation_id
                    )
                )
            ).scalars().first()
        if prog_or_var_quiz is None:
            prog_or_var_quiz = (
                await db.execute(
                    select(PreSessionQuizAssignment).where(
                        PreSessionQuizAssignment.program_id == program.id
                    )
                )
            ).scalars().first()
        if prog_or_var_quiz is not None and prog_or_var_quiz.preset_id is not None:
            db.add(PreSessionQuizAssignment(
                id=uuid.uuid4(),
                cohort_id=cohort.id,
                preset_id=prog_or_var_quiz.preset_id,
            ))

    if import_default_checklists:
        src_prog_id = checklist_source_program_id or program.id
        src_var: ProgramVariation | None = None
        if checklist_source_variation_id is not None:
            src_var = await var_svc.resolve_variation_for_program(
                db, src_prog_id, checklist_source_variation_id
            )
        elif src_prog_id == program.id:
            src_var = selected_var
        else:
            src_var = await var_svc.resolve_variation_for_program(db, src_prog_id, active_only=True)

        var_checklist_items = (
            list(
                (
                    await db.execute(
                        select(DeliveryChecklistItem)
                        .where(DeliveryChecklistItem.variation_id == src_var.id)
                        .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
                    )
                )
                .scalars()
                .all()
            )
            if src_var is not None
            else []
        )
        program_checklist_items = (
            var_checklist_items
            if var_checklist_items
            else list(
                (
                    await db.execute(
                        select(DeliveryChecklistItem)
                        .where(DeliveryChecklistItem.program_id == src_prog_id)
                        .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
                    )
                )
                .scalars()
                .all()
            )
        )
        for ci in program_checklist_items:
            db.add(day_service.clone_delivery_checklist_item(
                ci, actor_user_id=actor_user_id, cohort_id=cohort.id,
            ))
        if program_checklist_items:
            await db.flush()

        start_date = cohort.starts_on or date.today()
        if src_var is not None:
            v_days = await var_svc.variation_days(db, src_var.id)
            for idx, v_day in enumerate(v_days):
                sess_date = start_date + timedelta(days=idx)
                new_s = Session(
                    id=uuid.uuid4(),
                    cohort_id=cohort.id,
                    meeting_date=sess_date,
                    starts_at=v_day.starts_at,
                    title=v_day.title or f"Day {idx + 1}",
                    duration_hours=(
                        v_day.duration_hours
                        if v_day.duration_hours is not None
                        else (
                            cohort.duration_hours
                            if cohort.duration_hours is not None
                            else eff_scalars.get("duration_hours")
                        )
                    ),
                )
                db.add(new_s)
                await db.flush()

                d_items = (
                    await db.execute(
                        select(DeliveryChecklistItem)
                        .where(DeliveryChecklistItem.variation_day_id == v_day.id)
                        .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
                    )
                ).scalars().all()
                for ci in d_items:
                    db.add(day_service.clone_delivery_checklist_item(
                        ci, actor_user_id=actor_user_id, session_id=new_s.id,
                    ))
                copied_day_quiz = False
                if src_prog_id == program.id:
                    d_quiz = (
                        await db.execute(
                            select(PreSessionQuizAssignment).where(
                                PreSessionQuizAssignment.variation_day_id == v_day.id
                            )
                        )
                    ).scalars().first()
                    if d_quiz is not None:
                        db.add(PreSessionQuizAssignment(
                            id=uuid.uuid4(),
                            session_id=new_s.id,
                            preset_id=d_quiz.preset_id,
                        ))
                        copied_day_quiz = True
                if d_items or copied_day_quiz:
                    await db.flush()
        else:
            template_cohort = await day_service.find_program_template_cohort(
                db, src_prog_id, exclude_cohort_id=cohort.id,
            )
            if template_cohort:
                template_sessions = (
                    await db.execute(
                        select(Session)
                        .where(Session.cohort_id == template_cohort.id)
                        .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
                    )
                ).scalars().all()

                for idx, t_sess in enumerate(template_sessions):
                    sess_date = start_date + timedelta(days=idx)
                    new_s = Session(
                        id=uuid.uuid4(),
                        cohort_id=cohort.id,
                        meeting_date=sess_date,
                        starts_at=t_sess.starts_at,
                        title=t_sess.title or f"Day {idx + 1}",
                        duration_hours=(
                            t_sess.duration_hours
                            if t_sess.duration_hours is not None
                            else (
                                cohort.duration_hours
                                if cohort.duration_hours is not None
                                else program.duration_hours
                            )
                        ),
                    )
                    db.add(new_s)
                    await db.flush()

                    t_items = (
                        await db.execute(
                            select(DeliveryChecklistItem)
                            .where(DeliveryChecklistItem.session_id == t_sess.id)
                            .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
                        )
                    ).scalars().all()
                    for ci in t_items:
                        db.add(day_service.clone_delivery_checklist_item(
                            ci, actor_user_id=actor_user_id, session_id=new_s.id,
                        ))
                    copied_sess_quiz = False
                    if src_prog_id == program.id:
                        t_sess_quiz = (
                            await db.execute(
                                select(PreSessionQuizAssignment).where(
                                    PreSessionQuizAssignment.session_id == t_sess.id
                                )
                            )
                        ).scalars().first()
                        if t_sess_quiz is not None:
                            db.add(PreSessionQuizAssignment(
                                id=uuid.uuid4(),
                                session_id=new_s.id,
                                preset_id=t_sess_quiz.preset_id,
                            ))
                            copied_sess_quiz = True
                    if t_items or copied_sess_quiz:
                        await db.flush()

                if prog_or_var_quiz is None and src_prog_id == program.id:
                    t_cohort_quiz = (
                        await db.execute(
                            select(PreSessionQuizAssignment).where(
                                PreSessionQuizAssignment.cohort_id == template_cohort.id
                            )
                        )
                    ).scalars().first()
                    if t_cohort_quiz is not None:
                        db.add(PreSessionQuizAssignment(
                            id=uuid.uuid4(),
                            cohort_id=cohort.id,
                            preset_id=t_cohort_quiz.preset_id,
                        ))

                if not program_checklist_items:
                    template_cohort_items = (
                        await db.execute(
                            select(DeliveryChecklistItem)
                            .where(DeliveryChecklistItem.cohort_id == template_cohort.id)
                            .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
                        )
                    ).scalars().all()
                    for ci in template_cohort_items:
                        db.add(day_service.clone_delivery_checklist_item(
                            ci, actor_user_id=actor_user_id, cohort_id=cohort.id,
                        ))
                    if template_cohort_items:
                        await db.flush()

    if ensure_lms_override:
        lms_prog = (
            await db.execute(select(LmsProgram).where(LmsProgram.program_id == program.id))
        ).scalars().first()
        if lms_prog is None:
            lms_prog = LmsProgram(program_id=program.id, name=program.name)
            db.add(lms_prog)
            await db.flush()
        existing_ov = await db.scalar(
            select(LmsProgramCohortOverride.id).where(LmsProgramCohortOverride.cohort_id == cohort.id)
        )
        if existing_ov is None:
            db.add(LmsProgramCohortOverride(cohort_id=cohort.id, lms_program_id=lms_prog.id))
            await db.flush()
