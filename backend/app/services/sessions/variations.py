"""Program variations domain service (Option A — first-class defaults per variant).

Replaces the legacy hidden '[Template] ...' draft cohort hack with
`ProgramVariation` and `ProgramVariationDay`. Supports sparse overrides on
scalar/config fields (NULL inherits from parent Program) plus copying from a
blank start, another variation, or any existing cohort across any program.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructor_assessment.assignment import AssessmentCohortAssignment
from app.models.competitions.hint_station import CohortHintCard, CohortHintChallenge
from app.models.competitions.judging import CompetitionRubric, CompetitionRubricCriterion
from app.models.lms.program import LmsProgram, LmsProgramCohortOverride, LmsProgramItem
from app.models.missions.component_config import DesignComponentConfig
from app.models.sessions.checklist import DeliveryChecklistItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.cohort_opening import CohortOpening
from app.models.sessions.material import Material
from app.models.sessions.pre_session_quiz import PreSessionQuizAssignment
from app.models.sessions.program import Program
from app.models.sessions.program_opening import ProgramOpening
from app.models.sessions.program_variation import ProgramVariation, ProgramVariationDay
from app.models.sessions.session import Session
from app.services import storage
from app.services.sessions.day import clone_delivery_checklist_item

logger = logging.getLogger(__name__)

PROGRAM_ITEM_PDF_BUCKET = "lms-attachments"

SCALAR_OVERRIDE_FIELDS = (
    "duration_hours",
    "default_capacity",
    "poster_template_url",
    "keep_course_access_after_completion",
    "pricing_model",
    "price",
    "completion_rule_type",
    "completion_rule_value",
    "default_assessment_config_id",
    "default_certificate_template_id",
    "default_team_certificate_template_id",
)


def resolve_effective_scalars(
    program: Program,
    variation: ProgramVariation | None = None,
    cohort: Cohort | None = None,
) -> dict[str, Any]:
    """Resolve scalar settings along cohort -> variation -> program (first non-NULL wins)."""

    def pick(cohort_attr: str | None, var_attr: str, prog_attr: str | None = None):
        if cohort is not None and cohort_attr:
            val = getattr(cohort, cohort_attr, None)
            if val is not None:
                return val
        if variation is not None:
            val = getattr(variation, var_attr, None)
            if val is not None:
                return val
        return getattr(program, prog_attr or var_attr, None)

    return {
        "duration_hours": pick("duration_hours", "duration_hours"),
        "capacity": pick("capacity", "default_capacity"),
        "poster_template_url": pick("poster_template_url", "poster_template_url"),
        "keep_course_access_after_completion": pick(
            "keep_course_access_after_completion", "keep_course_access_after_completion"
        ),
        "pricing_model": pick("pricing_model", "pricing_model"),
        "price": pick("price", "price"),
        "completion_rule_type": pick("completion_rule_type", "completion_rule_type"),
        "completion_rule_value": pick("completion_rule_value", "completion_rule_value"),
        "default_assessment_config_id": (
            getattr(variation, "default_assessment_config_id", None)
            if variation is not None and getattr(variation, "default_assessment_config_id", None) is not None
            else getattr(program, "default_assessment_config_id", None)
        ),
        "default_certificate_template_id": pick(
            "default_certificate_template_id", "default_certificate_template_id"
        ),
        "default_team_certificate_template_id": pick(
            "default_team_certificate_template_id", "default_team_certificate_template_id"
        ),
    }


async def resolve_variation_for_program(
    db: AsyncSession,
    program_id: UUID,
    variation_id: UUID | None = None,
    *,
    active_only: bool = False,
) -> ProgramVariation | None:
    """Resolve explicit variation_id (validated against program_id) or the program's default/first variation."""
    if variation_id is not None:
        var = await db.get(ProgramVariation, variation_id)
        if var is None or var.program_id != program_id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Program variation not found for this program",
            )
        return var

    stmt = select(ProgramVariation).where(ProgramVariation.program_id == program_id)
    if active_only:
        stmt = stmt.where(ProgramVariation.is_active.is_(True))
    stmt = stmt.order_by(
        ProgramVariation.is_default.desc(),
        ProgramVariation.sort_order.asc(),
        ProgramVariation.created_at.asc(),
    )
    var = await db.scalar(stmt.limit(1))
    if var is None and active_only:
        # Fallback to any default/first variation even if inactive when no active ones exist
        var = await db.scalar(
            select(ProgramVariation)
            .where(ProgramVariation.program_id == program_id)
            .order_by(
                ProgramVariation.is_default.desc(),
                ProgramVariation.sort_order.asc(),
                ProgramVariation.created_at.asc(),
            )
            .limit(1)
        )
    return var


async def get_or_create_default_variation(
    db: AsyncSession, program_id: UUID, *, name: str = "Default"
) -> ProgramVariation:
    """Find the program's default variation, or create one if none exists yet."""
    existing = await resolve_variation_for_program(db, program_id)
    if existing is not None:
        return existing
    var = ProgramVariation(
        id=uuid.uuid4(),
        program_id=program_id,
        name=name,
        is_default=True,
        is_active=True,
        sort_order=1,
    )
    db.add(var)
    await db.flush()
    return var


async def variation_days(db: AsyncSession, variation_id: UUID) -> list[ProgramVariationDay]:
    return list((await db.execute(
        select(ProgramVariationDay)
        .where(ProgramVariationDay.variation_id == variation_id)
        .order_by(ProgramVariationDay.day_number.asc(), ProgramVariationDay.created_at.asc())
    )).scalars().all())


async def serialize_variation(
    db: AsyncSession,
    variation: ProgramVariation,
    *,
    days: list[ProgramVariationDay] | None = None,
    cohorts_count: int | None = None,
) -> dict[str, Any]:
    if days is None:
        days = await variation_days(db, variation.id)
    if cohorts_count is None:
        cohorts_count = int(await db.scalar(
            select(func.count(Cohort.id)).where(
                Cohort.variation_id == variation.id,
                Cohort.is_template_legacy.is_(False),
                Cohort.status != "draft",
                ~Cohort.name.ilike("[Template]%"),
            )
        ) or 0)
    return {
        "id": variation.id,
        "program_id": variation.program_id,
        "name": variation.name,
        "description": variation.description,
        "is_default": bool(variation.is_default),
        "is_active": bool(variation.is_active),
        "sort_order": variation.sort_order,
        "duration_hours": variation.duration_hours,
        "default_capacity": variation.default_capacity,
        "poster_template_url": variation.poster_template_url,
        "keep_course_access_after_completion": variation.keep_course_access_after_completion,
        "pricing_model": variation.pricing_model,
        "price": variation.price,
        "completion_rule_type": variation.completion_rule_type,
        "completion_rule_value": variation.completion_rule_value,
        "default_assessment_config_id": variation.default_assessment_config_id,
        "default_certificate_template_id": variation.default_certificate_template_id,
        "default_team_certificate_template_id": variation.default_team_certificate_template_id,
        "created_at": variation.created_at,
        "days": [
            {
                "id": d.id,
                "variation_id": d.variation_id,
                "day_number": d.day_number,
                "title": d.title,
                "duration_hours": d.duration_hours,
                "starts_at": d.starts_at,
                "created_at": d.created_at,
            }
            for d in days
        ],
        "days_count": len(days),
        "cohorts_count": cohorts_count,
    }


async def list_variations(
    db: AsyncSession, program_id: UUID, *, active_only: bool = False
) -> list[dict[str, Any]]:
    stmt = select(ProgramVariation).where(ProgramVariation.program_id == program_id)
    if active_only:
        stmt = stmt.where(ProgramVariation.is_active.is_(True))
    variations = list((await db.execute(
        stmt.order_by(
            ProgramVariation.is_default.desc(),
            ProgramVariation.sort_order.asc(),
            ProgramVariation.created_at.asc(),
        )
    )).scalars().all())
    if not variations:
        return []

    var_ids = [v.id for v in variations]
    day_rows = (await db.execute(
        select(ProgramVariationDay)
        .where(ProgramVariationDay.variation_id.in_(var_ids))
        .order_by(ProgramVariationDay.day_number.asc(), ProgramVariationDay.created_at.asc())
    )).scalars().all()
    days_by_var: dict[UUID, list[ProgramVariationDay]] = {}
    for d in day_rows:
        days_by_var.setdefault(d.variation_id, []).append(d)

    count_rows = (await db.execute(
        select(Cohort.variation_id, func.count(Cohort.id))
        .where(
            Cohort.variation_id.in_(var_ids),
            Cohort.is_template_legacy.is_(False),
            Cohort.status != "draft",
            ~Cohort.name.ilike("[Template]%"),
        )
        .group_by(Cohort.variation_id)
    )).all()
    counts_by_var = {vid: int(cnt) for vid, cnt in count_rows}

    return [
        await serialize_variation(
            db,
            v,
            days=days_by_var.get(v.id, []),
            cohorts_count=counts_by_var.get(v.id, 0),
        )
        for v in variations
    ]


async def _clear_other_defaults(db: AsyncSession, program_id: UUID, keep_variation_id: UUID) -> None:
    siblings = (await db.execute(
        select(ProgramVariation).where(
            ProgramVariation.program_id == program_id,
            ProgramVariation.id != keep_variation_id,
            ProgramVariation.is_default.is_(True),
        )
    )).scalars().all()
    for s in siblings:
        s.is_default = False


async def _clone_lms_items_to_variation(
    db: AsyncSession,
    source_items: list[LmsProgramItem],
    target_program_id: UUID,
    target_variation_id: UUID,
) -> None:
    if not source_items:
        return
    # Ensure parent LmsProgram exists on target program (program-level container).
    target_lms = await db.scalar(select(LmsProgram).where(LmsProgram.program_id == target_program_id))
    if target_lms is None:
        target_lms = LmsProgram(id=uuid.uuid4(), program_id=target_program_id)
        db.add(target_lms)
        await db.flush()

    for idx, item in enumerate(source_items, start=1):
        copy_id = uuid.uuid4()
        copy_pdf_path = None
        if item.pdf_path:
            try:
                data = await storage.download_file(PROGRAM_ITEM_PDF_BUCKET, item.pdf_path)
                filename = item.pdf_path.rsplit("/", 1)[-1]
                copy_pdf_path = await storage.upload_to_path(
                    PROGRAM_ITEM_PDF_BUCKET, f"program-items/{copy_id}/{filename}", data, "application/pdf",
                )
            except Exception as exc:
                logger.warning("Could not duplicate PDF %s while cloning variation LMS item: %s", item.pdf_path, exc)
                copy_pdf_path = item.pdf_path

        db.add(LmsProgramItem(
            id=copy_id,
            owner_type="variation",
            owner_id=target_variation_id,
            position=idx,
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
            max_team_size=getattr(item, "max_team_size", None),
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
            arcade_game_id=item.arcade_game_id,
            arcade_game_mode=item.arcade_game_mode,
            book_id=item.book_id,
            book_edition_id=getattr(item, "book_edition_id", None),
            book_profile=item.book_profile,
            book_chapter=item.book_chapter,
            book_chapters=getattr(item, "book_chapters", None),
            book_min_completion_pct=item.book_min_completion_pct,
        ))
    await db.flush()


async def _clone_hint_challenges(
    db: AsyncSession,
    src_owner_type: str,
    src_owner_id: UUID,
    dst_owner_id: UUID,
) -> bool:
    challenges = list((await db.execute(
        select(CohortHintChallenge)
        .where(
            CohortHintChallenge.owner_type == src_owner_type,
            CohortHintChallenge.owner_id == src_owner_id,
        )
        .order_by(CohortHintChallenge.position, CohortHintChallenge.created_at)
    )).scalars().all())
    if not challenges:
        return False

    c_ids = [c.id for c in challenges]
    cards = (await db.execute(
        select(CohortHintCard)
        .where(CohortHintCard.challenge_id.in_(c_ids))
        .order_by(CohortHintCard.unlock_order, CohortHintCard.position)
    )).scalars().all()
    cards_by_c: dict[UUID, list[CohortHintCard]] = {}
    for card in cards:
        cards_by_c.setdefault(card.challenge_id, []).append(card)

    for ch in challenges:
        new_ch = CohortHintChallenge(
            id=uuid.uuid4(),
            owner_type="variation",
            owner_id=dst_owner_id,
            title=ch.title,
            challenge_code=ch.challenge_code,
            topic=ch.topic,
            description=ch.description,
            mission_statement=ch.mission_statement,
            max_points=ch.max_points,
            position=ch.position,
            is_active=ch.is_active,
        )
        db.add(new_ch)
        await db.flush()
        for card in cards_by_c.get(ch.id, []):
            db.add(CohortHintCard(
                id=uuid.uuid4(),
                challenge_id=new_ch.id,
                level=card.level,
                level_label=card.level_label,
                badge_label=card.badge_label,
                title=card.title,
                teaser=card.teaser,
                revealed_content=card.revealed_content,
                point_deduction=card.point_deduction,
                unlock_order=card.unlock_order,
                position=card.position,
            ))
    await db.flush()
    return True


async def _clone_rubric(
    db: AsyncSession,
    src_rubric: CompetitionRubric | None,
    dst_program_id: UUID,
    dst_variation_id: UUID,
) -> None:
    if src_rubric is None:
        return
    new_rubric = CompetitionRubric(
        id=uuid.uuid4(),
        program_id=dst_program_id,
        variation_id=dst_variation_id,
        cohort_id=None,
        name=src_rubric.name,
    )
    db.add(new_rubric)
    await db.flush()
    criteria = (await db.execute(
        select(CompetitionRubricCriterion)
        .where(CompetitionRubricCriterion.rubric_id == src_rubric.id)
        .order_by(CompetitionRubricCriterion.position)
    )).scalars().all()
    for crit in criteria:
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
    if criteria:
        await db.flush()


async def copy_variation_contents(
    db: AsyncSession,
    *,
    source: ProgramVariation,
    target: ProgramVariation,
    carry: set[str],
    actor_user_id: UUID,
    include_rates: bool = True,
) -> None:
    """Copy chosen configuration buckets from one ProgramVariation to another."""
    if "scalars" in carry:
        for f in (
            "duration_hours",
            "default_capacity",
            "poster_template_url",
            "keep_course_access_after_completion",
            "pricing_model",
            "price",
            "completion_rule_type",
            "completion_rule_value",
        ):
            val = getattr(source, f)
            if getattr(target, f) is None and val is not None:
                setattr(target, f, val)

    if "assessment" in carry and target.default_assessment_config_id is None:
        target.default_assessment_config_id = source.default_assessment_config_id

    if "certificate" in carry:
        if target.default_certificate_template_id is None:
            target.default_certificate_template_id = source.default_certificate_template_id
        if target.default_team_certificate_template_id is None:
            target.default_team_certificate_template_id = source.default_team_certificate_template_id

    if "days" in carry:
        var_items = (await db.execute(
            select(DeliveryChecklistItem)
            .where(DeliveryChecklistItem.variation_id == source.id)
            .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
        )).scalars().all()
        for ci in var_items:
            db.add(clone_delivery_checklist_item(
                ci, actor_user_id=actor_user_id, variation_id=target.id,
            ))

        src_days = await variation_days(db, source.id)
        for d in src_days:
            new_day = ProgramVariationDay(
                id=uuid.uuid4(),
                variation_id=target.id,
                day_number=d.day_number,
                title=d.title,
                duration_hours=d.duration_hours,
                starts_at=d.starts_at,
            )
            db.add(new_day)
            await db.flush()

            d_items = (await db.execute(
                select(DeliveryChecklistItem)
                .where(DeliveryChecklistItem.variation_day_id == d.id)
                .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
            )).scalars().all()
            for ci in d_items:
                db.add(clone_delivery_checklist_item(
                    ci, actor_user_id=actor_user_id, variation_day_id=new_day.id,
                ))

            if "pre_quiz" in carry:
                d_quiz = await db.scalar(
                    select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.variation_day_id == d.id)
                )
                if d_quiz is not None:
                    db.add(PreSessionQuizAssignment(
                        id=uuid.uuid4(),
                        variation_day_id=new_day.id,
                        preset_id=d_quiz.preset_id,
                    ))

    if "pre_quiz" in carry:
        v_quiz = await db.scalar(
            select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.variation_id == source.id)
        )
        if v_quiz is not None:
            db.add(PreSessionQuizAssignment(
                id=uuid.uuid4(),
                variation_id=target.id,
                preset_id=v_quiz.preset_id,
            ))

    if "roles" in carry:
        openings = (await db.execute(
            select(ProgramOpening).where(ProgramOpening.variation_id == source.id)
        )).scalars().all()
        for op in openings:
            db.add(ProgramOpening(
                id=uuid.uuid4(),
                variation_id=target.id,
                role_id=op.role_id,
                slots=op.slots,
                amount_aed=(op.amount_aed if include_rates else None),
                notes=op.notes,
                responsibilities_override=op.responsibilities_override,
                created_by=actor_user_id,
            ))

    if "lms" in carry:
        items = list((await db.execute(
            select(LmsProgramItem)
            .where(LmsProgramItem.owner_type == "variation", LmsProgramItem.owner_id == source.id)
            .order_by(LmsProgramItem.position)
        )).scalars().all())
        await _clone_lms_items_to_variation(db, items, target.program_id, target.id)

    if "component_config" in carry:
        cfg = await db.scalar(
            select(DesignComponentConfig).where(
                DesignComponentConfig.owner_type == "variation",
                DesignComponentConfig.owner_id == source.id,
            )
        )
        if cfg is not None:
            db.add(DesignComponentConfig(
                id=uuid.uuid4(),
                owner_type="variation",
                owner_id=target.id,
                disabled_subsystems=list(cfg.disabled_subsystems or []),
                disabled_tags=list(cfg.disabled_tags or []),
                disabled_component_ids=list(cfg.disabled_component_ids or []),
                updated_by=actor_user_id,
            ))

    if "hints" in carry:
        await _clone_hint_challenges(db, "variation", source.id, target.id)

    if "materials" in carry:
        mats = (await db.execute(
            select(Material)
            .where(Material.variation_id == source.id)
            .order_by(Material.sort_order, Material.created_at)
        )).scalars().all()
        for m in mats:
            db.add(Material(
                id=uuid.uuid4(),
                variation_id=target.id,
                title=m.title,
                notes=m.notes,
                bucket=m.bucket,
                file_path=m.file_path,
                url=m.url,
                sort_order=m.sort_order,
                is_published=m.is_published,
                uploaded_by=actor_user_id,
            ))

    if "rubric" in carry:
        src_rubric = await db.scalar(
            select(CompetitionRubric).where(CompetitionRubric.variation_id == source.id)
        )
        await _clone_rubric(db, src_rubric, target.program_id, target.id)

    await db.flush()


async def _populate_variation_from_cohort(
    db: AsyncSession,
    *,
    source_cohort: Cohort,
    target: ProgramVariation,
    carry: set[str],
    actor_user_id: UUID,
    include_rates: bool = True,
) -> None:
    """Import configuration buckets into a new ProgramVariation from ANY cohort of ANY program."""
    src_prog = await db.get(Program, source_cohort.program_id)
    src_var = (
        await db.get(ProgramVariation, source_cohort.variation_id)
        if source_cohort.variation_id is not None else None
    )

    if "scalars" in carry and src_prog is not None:
        eff = resolve_effective_scalars(src_prog, src_var, source_cohort)
        scalar_map = (
            ("duration_hours", "duration_hours"),
            ("capacity", "default_capacity"),
            ("poster_template_url", "poster_template_url"),
            ("keep_course_access_after_completion", "keep_course_access_after_completion"),
            ("pricing_model", "pricing_model"),
            ("price", "price"),
            ("completion_rule_type", "completion_rule_type"),
            ("completion_rule_value", "completion_rule_value"),
        )
        for eff_key, var_attr in scalar_map:
            if getattr(target, var_attr) is None and eff.get(eff_key) is not None:
                setattr(target, var_attr, eff[eff_key])

    if "assessment" in carry and target.default_assessment_config_id is None:
        c_assn = await db.scalar(
            select(AssessmentCohortAssignment).where(AssessmentCohortAssignment.cohort_id == source_cohort.id)
        )
        if c_assn is not None:
            target.default_assessment_config_id = c_assn.config_id
        elif src_var and src_var.default_assessment_config_id is not None:
            target.default_assessment_config_id = src_var.default_assessment_config_id
        elif src_prog and src_prog.default_assessment_config_id is not None:
            target.default_assessment_config_id = src_prog.default_assessment_config_id

    if "certificate" in carry:
        if target.default_certificate_template_id is None:
            target.default_certificate_template_id = (
                source_cohort.default_certificate_template_id
                or (src_var.default_certificate_template_id if src_var else None)
                or (src_prog.default_certificate_template_id if src_prog else None)
            )
        if target.default_team_certificate_template_id is None:
            target.default_team_certificate_template_id = (
                source_cohort.default_team_certificate_template_id
                or (src_var.default_team_certificate_template_id if src_var else None)
                or (src_prog.default_team_certificate_template_id if src_prog else None)
            )

    if "days" in carry:
        # Cohort-level delivery checklist items (fall back to source variation/program if cross-program & cohort empty)
        c_items = (await db.execute(
            select(DeliveryChecklistItem)
            .where(DeliveryChecklistItem.cohort_id == source_cohort.id)
            .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
        )).scalars().all()
        if not c_items and src_var is not None:
            c_items = (await db.execute(
                select(DeliveryChecklistItem)
                .where(DeliveryChecklistItem.variation_id == src_var.id)
                .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
            )).scalars().all()
        if not c_items and source_cohort.program_id != target.program_id:
            c_items = (await db.execute(
                select(DeliveryChecklistItem)
                .where(DeliveryChecklistItem.program_id == source_cohort.program_id)
                .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
            )).scalars().all()
        for ci in c_items:
            db.add(clone_delivery_checklist_item(ci, actor_user_id=actor_user_id, variation_id=target.id))

        sessions = list((await db.execute(
            select(Session)
            .where(Session.cohort_id == source_cohort.id)
            .order_by(Session.meeting_date, Session.starts_at, Session.created_at)
        )).scalars().all())
        src_var_days = await variation_days(db, src_var.id) if src_var is not None else []

        for idx, sess in enumerate(sessions, start=1):
            new_day = ProgramVariationDay(
                id=uuid.uuid4(),
                variation_id=target.id,
                day_number=idx,
                title=sess.title,
                duration_hours=sess.duration_hours,
                starts_at=sess.starts_at,
            )
            db.add(new_day)
            await db.flush()

            s_items = (await db.execute(
                select(DeliveryChecklistItem)
                .where(DeliveryChecklistItem.session_id == sess.id)
                .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
            )).scalars().all()
            if not s_items and (idx - 1) < len(src_var_days):
                s_items = (await db.execute(
                    select(DeliveryChecklistItem)
                    .where(DeliveryChecklistItem.variation_day_id == src_var_days[idx - 1].id)
                    .order_by(DeliveryChecklistItem.sort_order, DeliveryChecklistItem.created_at)
                )).scalars().all()
            for ci in s_items:
                db.add(clone_delivery_checklist_item(ci, actor_user_id=actor_user_id, variation_day_id=new_day.id))

            if "pre_quiz" in carry:
                s_quiz = await db.scalar(
                    select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.session_id == sess.id)
                )
                if s_quiz is None and (idx - 1) < len(src_var_days):
                    s_quiz = await db.scalar(
                        select(PreSessionQuizAssignment).where(
                            PreSessionQuizAssignment.variation_day_id == src_var_days[idx - 1].id
                        )
                    )
                if s_quiz is not None:
                    db.add(PreSessionQuizAssignment(
                        id=uuid.uuid4(),
                        variation_day_id=new_day.id,
                        preset_id=s_quiz.preset_id,
                    ))

    if "pre_quiz" in carry:
        c_quiz = await db.scalar(
            select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.cohort_id == source_cohort.id)
        )
        if c_quiz is None and src_var is not None:
            c_quiz = await db.scalar(
                select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.variation_id == src_var.id)
            )
        if c_quiz is None and source_cohort.program_id != target.program_id:
            c_quiz = await db.scalar(
                select(PreSessionQuizAssignment).where(PreSessionQuizAssignment.program_id == source_cohort.program_id)
            )
        if c_quiz is not None:
            db.add(PreSessionQuizAssignment(
                id=uuid.uuid4(),
                variation_id=target.id,
                preset_id=c_quiz.preset_id,
            ))

    if "roles" in carry:
        c_openings = (await db.execute(
            select(CohortOpening).where(CohortOpening.cohort_id == source_cohort.id)
        )).scalars().all()
        if c_openings:
            for op in c_openings:
                db.add(ProgramOpening(
                    id=uuid.uuid4(),
                    variation_id=target.id,
                    role_id=op.role_id,
                    slots=op.slots,
                    amount_aed=(op.amount_aed if include_rates else None),
                    notes=op.notes,
                    responsibilities_override=op.responsibilities_override,
                    created_by=actor_user_id,
                ))
        elif src_var is not None:
            v_openings = (await db.execute(
                select(ProgramOpening).where(ProgramOpening.variation_id == src_var.id)
            )).scalars().all()
            for op in v_openings:
                db.add(ProgramOpening(
                    id=uuid.uuid4(),
                    variation_id=target.id,
                    role_id=op.role_id,
                    slots=op.slots,
                    amount_aed=(op.amount_aed if include_rates else None),
                    notes=op.notes,
                    responsibilities_override=op.responsibilities_override,
                    created_by=actor_user_id,
                ))
        elif source_cohort.program_id != target.program_id:
            p_openings = (await db.execute(
                select(ProgramOpening).where(ProgramOpening.program_id == source_cohort.program_id)
            )).scalars().all()
            for op in p_openings:
                db.add(ProgramOpening(
                    id=uuid.uuid4(),
                    variation_id=target.id,
                    role_id=op.role_id,
                    slots=op.slots,
                    amount_aed=(op.amount_aed if include_rates else None),
                    notes=op.notes,
                    responsibilities_override=op.responsibilities_override,
                    created_by=actor_user_id,
                ))

    if "lms" in carry:
        # Pick cohort override -> variation -> source program LMS items
        items: list[LmsProgramItem] = []
        c_ovr = await db.scalar(
            select(LmsProgramCohortOverride).where(LmsProgramCohortOverride.cohort_id == source_cohort.id)
        )
        if c_ovr is not None:
            items = list((await db.execute(
                select(LmsProgramItem)
                .where(LmsProgramItem.owner_type == "cohort_override", LmsProgramItem.owner_id == c_ovr.id)
                .order_by(LmsProgramItem.position)
            )).scalars().all())
        if not items and src_var is not None:
            items = list((await db.execute(
                select(LmsProgramItem)
                .where(LmsProgramItem.owner_type == "variation", LmsProgramItem.owner_id == src_var.id)
                .order_by(LmsProgramItem.position)
            )).scalars().all())
        if not items:
            src_lms = await db.scalar(
                select(LmsProgram).where(LmsProgram.program_id == source_cohort.program_id)
            )
            if src_lms is not None:
                items = list((await db.execute(
                    select(LmsProgramItem)
                    .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == src_lms.id)
                    .order_by(LmsProgramItem.position)
                )).scalars().all())
        await _clone_lms_items_to_variation(db, items, target.program_id, target.id)

    if "component_config" in carry:
        cfg = await db.scalar(
            select(DesignComponentConfig).where(
                DesignComponentConfig.owner_type == "cohort",
                DesignComponentConfig.owner_id == source_cohort.id,
            )
        )
        if cfg is None and src_var is not None:
            cfg = await db.scalar(
                select(DesignComponentConfig).where(
                    DesignComponentConfig.owner_type == "variation",
                    DesignComponentConfig.owner_id == src_var.id,
                )
            )
        if cfg is None:
            src_lms = await db.scalar(
                select(LmsProgram).where(LmsProgram.program_id == source_cohort.program_id)
            )
            if src_lms is not None:
                cfg = await db.scalar(
                    select(DesignComponentConfig).where(
                        DesignComponentConfig.owner_type == "program",
                        DesignComponentConfig.owner_id == src_lms.id,
                    )
                )
        if cfg is not None:
            db.add(DesignComponentConfig(
                id=uuid.uuid4(),
                owner_type="variation",
                owner_id=target.id,
                disabled_subsystems=list(cfg.disabled_subsystems or []),
                disabled_tags=list(cfg.disabled_tags or []),
                disabled_component_ids=list(cfg.disabled_component_ids or []),
                updated_by=actor_user_id,
            ))

    if "hints" in carry:
        copied = await _clone_hint_challenges(db, "cohort", source_cohort.id, target.id)
        if not copied and src_var is not None:
            copied = await _clone_hint_challenges(db, "variation", src_var.id, target.id)
        if not copied:
            await _clone_hint_challenges(db, "program", source_cohort.program_id, target.id)

    if "materials" in carry:
        mats = (await db.execute(
            select(Material)
            .where(Material.cohort_id == source_cohort.id)
            .order_by(Material.sort_order, Material.created_at)
        )).scalars().all()
        if not mats and src_var is not None:
            mats = (await db.execute(
                select(Material)
                .where(Material.variation_id == src_var.id)
                .order_by(Material.sort_order, Material.created_at)
            )).scalars().all()
        if not mats and source_cohort.program_id != target.program_id:
            mats = (await db.execute(
                select(Material)
                .where(Material.program_id == source_cohort.program_id)
                .order_by(Material.sort_order, Material.created_at)
            )).scalars().all()
        for m in mats:
            db.add(Material(
                id=uuid.uuid4(),
                variation_id=target.id,
                title=m.title,
                notes=m.notes,
                bucket=m.bucket,
                file_path=m.file_path,
                url=m.url,
                sort_order=m.sort_order,
                is_published=m.is_published,
                uploaded_by=actor_user_id,
            ))

    if "rubric" in carry:
        src_rubric = await db.scalar(
            select(CompetitionRubric).where(CompetitionRubric.cohort_id == source_cohort.id)
        )
        if src_rubric is None and src_var is not None:
            src_rubric = await db.scalar(
                select(CompetitionRubric).where(CompetitionRubric.variation_id == src_var.id)
            )
        if src_rubric is None:
            src_rubric = await db.scalar(
                select(CompetitionRubric).where(
                    CompetitionRubric.program_id == source_cohort.program_id,
                    CompetitionRubric.variation_id.is_(None),
                    CompetitionRubric.cohort_id.is_(None),
                )
            )
        await _clone_rubric(db, src_rubric, target.program_id, target.id)

    await db.flush()


async def create_variation(
    db: AsyncSession,
    *,
    program_id: UUID,
    payload: dict[str, Any],
    actor_user_id: UUID,
    include_rates: bool = True,
) -> dict[str, Any]:
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program not found")

    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Variation name is required")

    mode = payload.get("mode") or "blank"
    carry = set(payload.get("carry") or [])

    existing_count = int(await db.scalar(
        select(func.count(ProgramVariation.id)).where(ProgramVariation.program_id == program_id)
    ) or 0)
    is_default = bool(payload.get("is_default")) or existing_count == 0
    max_order = int(await db.scalar(
        select(func.coalesce(func.max(ProgramVariation.sort_order), 0)).where(
            ProgramVariation.program_id == program_id
        )
    ) or 0)

    variation = ProgramVariation(
        id=uuid.uuid4(),
        program_id=program_id,
        name=name,
        description=payload.get("description"),
        is_default=is_default,
        is_active=bool(payload.get("is_active", True)),
        sort_order=payload.get("sort_order") if payload.get("sort_order") not in (None, 1) else (max_order + 1),
        **{f: payload.get(f) for f in SCALAR_OVERRIDE_FIELDS},
    )
    db.add(variation)
    await db.flush()

    if is_default:
        await _clear_other_defaults(db, program_id, variation.id)

    if mode == "duplicate":
        src_id = payload.get("source_variation_id")
        if src_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select a variation to duplicate")
        src_var = await db.get(ProgramVariation, src_id)
        if src_var is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source variation not found")
        await copy_variation_contents(
            db, source=src_var, target=variation, carry=carry, actor_user_id=actor_user_id, include_rates=include_rates,
        )
    elif mode == "from_cohort":
        src_cohort_id = payload.get("source_cohort_id")
        if src_cohort_id is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Select a source cohort to import from")
        src_cohort = await db.get(Cohort, src_cohort_id)
        if src_cohort is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Source cohort not found")
        await _populate_variation_from_cohort(
            db, source_cohort=src_cohort, target=variation, carry=carry, actor_user_id=actor_user_id, include_rates=include_rates,
        )

    await db.flush()
    return await serialize_variation(db, variation)


async def update_variation(
    db: AsyncSession, *, program_id: UUID, variation_id: UUID, payload: dict[str, Any]
) -> dict[str, Any]:
    var = await db.get(ProgramVariation, variation_id)
    if var is None or var.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program variation not found")

    if "name" in payload:
        name = (payload["name"] or "").strip()
        if not name:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Variation name cannot be empty")
        var.name = name

    for field in ("description", "is_active", "sort_order", *SCALAR_OVERRIDE_FIELDS):
        if field in payload:
            setattr(var, field, payload[field])

    if payload.get("is_default") is True:
        var.is_default = True
        await _clear_other_defaults(db, program_id, var.id)
    elif payload.get("is_default") is False:
        var.is_default = False

    await db.flush()
    return await serialize_variation(db, var)


async def delete_variation(db: AsyncSession, *, program_id: UUID, variation_id: UUID) -> None:
    var = await db.get(ProgramVariation, variation_id)
    if var is None or var.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program variation not found")

    was_default = bool(var.is_default)
    # Clean up polymorphic children that don't have SQL FK cascades to program_variations
    await db.execute(
        DesignComponentConfig.__table__.delete().where(
            DesignComponentConfig.owner_type == "variation",
            DesignComponentConfig.owner_id == variation_id,
        )
    )
    await db.execute(
        LmsProgramItem.__table__.delete().where(
            LmsProgramItem.owner_type == "variation",
            LmsProgramItem.owner_id == variation_id,
        )
    )
    challenges = (await db.execute(
        select(CohortHintChallenge).where(
            CohortHintChallenge.owner_type == "variation",
            CohortHintChallenge.owner_id == variation_id,
        )
    )).scalars().all()
    for ch in challenges:
        await db.delete(ch)

    await db.delete(var)
    await db.flush()

    if was_default:
        nxt = await db.scalar(
            select(ProgramVariation)
            .where(ProgramVariation.program_id == program_id)
            .order_by(ProgramVariation.sort_order.asc(), ProgramVariation.created_at.asc())
            .limit(1)
        )
        if nxt is not None:
            nxt.is_default = True
            await db.flush()


async def add_variation_day(
    db: AsyncSession,
    *,
    program_id: UUID,
    variation_id: UUID,
    title: str | None = None,
    duration_hours=None,
    starts_at=None,
    day_number: int | None = None,
) -> ProgramVariationDay:
    var = await db.get(ProgramVariation, variation_id)
    if var is None or var.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program variation not found")

    max_day = int(await db.scalar(
        select(func.coalesce(func.max(ProgramVariationDay.day_number), 0)).where(
            ProgramVariationDay.variation_id == variation_id
        )
    ) or 0)
    num = day_number if day_number is not None else (max_day + 1)
    day = ProgramVariationDay(
        id=uuid.uuid4(),
        variation_id=variation_id,
        day_number=num,
        title=title or f"Day {num}",
        duration_hours=duration_hours,
        starts_at=starts_at,
    )
    db.add(day)
    await db.flush()
    return day


async def update_variation_day(
    db: AsyncSession, *, program_id: UUID, variation_id: UUID, day_id: UUID, payload: dict[str, Any]
) -> ProgramVariationDay:
    var = await db.get(ProgramVariation, variation_id)
    if var is None or var.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program variation not found")
    day = await db.get(ProgramVariationDay, day_id)
    if day is None or day.variation_id != variation_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Variation day not found")

    for f in ("title", "duration_hours", "starts_at", "day_number"):
        if f in payload:
            setattr(day, f, payload[f])
    await db.flush()
    return day


async def delete_variation_day(
    db: AsyncSession, *, program_id: UUID, variation_id: UUID, day_id: UUID
) -> None:
    var = await db.get(ProgramVariation, variation_id)
    if var is None or var.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program variation not found")
    day = await db.get(ProgramVariationDay, day_id)
    if day is None or day.variation_id != variation_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Variation day not found")

    await db.delete(day)
    await db.flush()

    remaining = await variation_days(db, variation_id)
    # Shift via negative temporary numbers to stay clear of UNIQUE(variation_id, day_number)
    for idx, d in enumerate(remaining, start=1):
        if d.day_number != idx:
            d.day_number = -idx
    await db.flush()
    for idx, d in enumerate(remaining, start=1):
        if d.day_number != idx:
            d.day_number = idx
    await db.flush()


async def reorder_variation_days(
    db: AsyncSession, *, program_id: UUID, variation_id: UUID, day_ids: list[UUID]
) -> list[ProgramVariationDay]:
    var = await db.get(ProgramVariation, variation_id)
    if var is None or var.program_id != program_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Program variation not found")
    days = await variation_days(db, variation_id)
    by_id = {d.id: d for d in days}
    if len(day_ids) != len(days) or set(day_ids) != set(by_id.keys()):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="day_ids must match all days of this variation",
        )
    for idx, did in enumerate(day_ids, start=1):
        by_id[did].day_number = -idx
    await db.flush()
    for idx, did in enumerate(day_ids, start=1):
        by_id[did].day_number = idx
    await db.flush()
    return [by_id[did] for did in day_ids]
