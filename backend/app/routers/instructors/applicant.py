import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.dependencies import require_applicant
from app.db.session import get_db
from app.models.enums import ApplicationStatus, ModuleSubmissionStatus, VideoSubmissionStatus
from app.models.instructors.application_review import ApplicationReview
from app.models.instructors.checklist import ChecklistItem, ChecklistModule, ModuleSection, UserChecklistProgress
from app.models.instructors.module_submission import ModuleSubmission
from app.models.instructors.presentation_submission import PresentationSubmission
from app.models.instructors.video_submission import VideoSubmission
from app.models.user import User
from app.schemas.instructors.applicant import (
    ApplicationStatusOut,
    ChecklistItemProgressOut,
    ChecklistModuleOut,
    ModuleSectionOut,
    ModuleSubmissionOut,
    PresentationSubmit,
    VideoSubmissionOut,
    VideoSummaryUpdate,
)
from app.services import storage

router = APIRouter(tags=["instructors-applicant"])

MIN_SUMMARY_WORDS = 200


async def _get_review(db: AsyncSession, user_id: uuid.UUID) -> ApplicationReview:
    review = (await db.execute(select(ApplicationReview).where(ApplicationReview.user_id == user_id))).scalars().first()
    if not review:
        raise HTTPException(status_code=404, detail="Application not found")
    return review


async def _all_videos_submitted(db: AsyncSession, user_id: uuid.UUID) -> bool:
    rows = (await db.execute(select(VideoSubmission).where(VideoSubmission.user_id == user_id))).scalars().all()
    return len(rows) > 0 and all(v.status == VideoSubmissionStatus.submitted for v in rows)


async def _all_modules_submitted(db: AsyncSession, user_id: uuid.UUID) -> bool:
    total = (await db.execute(select(ChecklistModule.id))).scalars().all()
    if not total:
        return False
    submitted = (await db.execute(
        select(ModuleSubmission.module_id).where(
            ModuleSubmission.user_id == user_id,
            ModuleSubmission.status != ModuleSubmissionStatus.rejected,
        )
    )).scalars().all()
    return set(total) <= set(submitted)


# ── Phase 1: video summaries ──────────────────────────────────

@router.get("/videos", response_model=list[VideoSubmissionOut])
async def list_videos(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    rows = (await db.execute(
        select(VideoSubmission).where(VideoSubmission.user_id == current_user.id).order_by(VideoSubmission.video_no)
    )).scalars().all()
    return list(rows)


@router.put("/videos/{video_no}", response_model=VideoSubmissionOut)
async def update_video(
    video_no: int,
    body: VideoSummaryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    video = (await db.execute(
        select(VideoSubmission).where(VideoSubmission.user_id == current_user.id, VideoSubmission.video_no == video_no)
    )).scalars().first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    word_count = len((body.summary_text or "").split())
    video.youtube_url = body.youtube_url
    video.summary_text = body.summary_text
    video.word_count = word_count

    if body.submit:
        if word_count < MIN_SUMMARY_WORDS:
            raise HTTPException(status_code=400, detail=f"Summary must be at least {MIN_SUMMARY_WORDS} words")
        video.status = VideoSubmissionStatus.submitted
        video.submitted_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(video)
    return video


# ── Phase 1: checklist modules ────────────────────────────────

@router.get("/modules", response_model=list[ChecklistModuleOut])
async def list_modules(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    modules = (await db.execute(select(ChecklistModule).order_by(ChecklistModule.sort_order))).scalars().all()
    module_ids = [m.id for m in modules]

    items = (await db.execute(select(ChecklistItem).where(ChecklistItem.module_id.in_(module_ids)))).scalars().all()
    items_by_module: dict[uuid.UUID, list] = {}
    for it in items:
        items_by_module.setdefault(it.module_id, []).append(it)

    item_ids = [it.id for it in items]
    progress_rows = (await db.execute(
        select(UserChecklistProgress).where(
            UserChecklistProgress.user_id == current_user.id,
            UserChecklistProgress.checklist_item_id.in_(item_ids),
        )
    )).scalars().all()
    completed_ids = {p.checklist_item_id for p in progress_rows if p.is_completed}

    submissions = (await db.execute(
        select(ModuleSubmission).where(
            ModuleSubmission.user_id == current_user.id, ModuleSubmission.module_id.in_(module_ids)
        )
    )).scalars().all()
    submission_by_module = {s.module_id: s for s in submissions}

    out = []
    for m in modules:
        mod_items = items_by_module.get(m.id, [])
        sub = submission_by_module.get(m.id)
        out.append(ChecklistModuleOut(
            id=m.id,
            title=m.title,
            sort_order=m.sort_order,
            item_count=len(mod_items),
            completed_count=sum(1 for it in mod_items if it.id in completed_ids),
            submission_status=sub.status if sub else None,
            submission_feedback=sub.feedback if sub else None,
        ))
    return out


@router.get("/modules/{module_id}", response_model=ChecklistModuleOut)
async def module_detail(
    module_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)
):
    module = (await db.execute(select(ChecklistModule).where(ChecklistModule.id == module_id))).scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    sections = (await db.execute(
        select(ModuleSection).where(ModuleSection.module_id == module_id).order_by(ModuleSection.sort_order)
    )).scalars().all()
    items = (await db.execute(
        select(ChecklistItem).where(ChecklistItem.module_id == module_id).order_by(ChecklistItem.sort_order)
    )).scalars().all()
    progress_rows = (await db.execute(
        select(UserChecklistProgress).where(
            UserChecklistProgress.user_id == current_user.id,
            UserChecklistProgress.checklist_item_id.in_([it.id for it in items]),
        )
    )).scalars().all()
    completed_ids = {p.checklist_item_id for p in progress_rows if p.is_completed}

    def _item_out(it: ChecklistItem) -> ChecklistItemProgressOut:
        return ChecklistItemProgressOut(
            id=it.id, item_code=it.item_code, title=it.title, description=it.description,
            is_required=it.is_required, is_completed=it.id in completed_ids,
        )

    section_groups: list[ModuleSectionOut] = []
    no_section_items = [it for it in items if it.section_id is None]
    if no_section_items:
        section_groups.append(ModuleSectionOut(id=None, title=None, items=[_item_out(it) for it in no_section_items]))
    for sec in sections:
        sec_items = [it for it in items if it.section_id == sec.id]
        section_groups.append(ModuleSectionOut(id=sec.id, title=sec.title, items=[_item_out(it) for it in sec_items]))

    sub = (await db.execute(
        select(ModuleSubmission).where(ModuleSubmission.user_id == current_user.id, ModuleSubmission.module_id == module_id)
    )).scalars().first()

    return ChecklistModuleOut(
        id=module.id, title=module.title, sort_order=module.sort_order, sections=section_groups,
        item_count=len(items), completed_count=sum(1 for it in items if it.id in completed_ids),
        submission_status=sub.status if sub else None, submission_feedback=sub.feedback if sub else None,
    )


@router.put("/checklist/items/{item_id}/toggle")
async def toggle_checklist_item(
    item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)
):
    item = (await db.execute(select(ChecklistItem).where(ChecklistItem.id == item_id))).scalars().first()
    if not item:
        raise HTTPException(status_code=404, detail="Checklist item not found")

    progress = (await db.execute(
        select(UserChecklistProgress).where(
            UserChecklistProgress.user_id == current_user.id, UserChecklistProgress.checklist_item_id == item_id
        )
    )).scalars().first()
    if not progress:
        progress = UserChecklistProgress(user_id=current_user.id, checklist_item_id=item_id, is_completed=True)
        db.add(progress)
    else:
        progress.is_completed = not progress.is_completed

    await db.commit()
    return {"id": str(item_id), "is_completed": progress.is_completed}


@router.post("/modules/{module_id}/submit", response_model=ModuleSubmissionOut)
async def submit_module(
    module_id: uuid.UUID,
    file: UploadFile,
    notes_text: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_applicant),
):
    if not await _all_videos_submitted(db, current_user.id):
        raise HTTPException(status_code=400, detail="Submit all 3 video summaries before uploading modules")

    module = (await db.execute(select(ChecklistModule).where(ChecklistModule.id == module_id))).scalars().first()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")

    data = await file.read()
    path = f"{current_user.id}/{module_id}/{file.filename}"
    file_url = await storage.upload_file("applicant-submissions", path, data, file.content_type or "application/pdf")

    existing = (await db.execute(
        select(ModuleSubmission).where(ModuleSubmission.user_id == current_user.id, ModuleSubmission.module_id == module_id)
    )).scalars().first()
    if existing:
        existing.file_url = file_url
        existing.original_filename = file.filename
        existing.notes_text = notes_text
        existing.status = ModuleSubmissionStatus.submitted
        existing.feedback = None
        existing.submitted_at = datetime.now(timezone.utc)
        submission = existing
    else:
        submission = ModuleSubmission(
            user_id=current_user.id, module_id=module_id, file_url=file_url,
            original_filename=file.filename, notes_text=notes_text,
        )
        db.add(submission)

    await db.commit()
    await db.refresh(submission)
    return submission


# ── Application submit / reopen / status ──────────────────────

@router.post("/application/submit", response_model=ApplicationStatusOut)
async def submit_application(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    review = await _get_review(db, current_user.id)
    if review.status != ApplicationStatus.in_progress:
        raise HTTPException(status_code=400, detail="Application has already been submitted")
    if not await _all_videos_submitted(db, current_user.id):
        raise HTTPException(status_code=400, detail="Submit all 3 video summaries first")
    if not await _all_modules_submitted(db, current_user.id):
        raise HTTPException(status_code=400, detail="Submit all checklist modules first")

    review.status = ApplicationStatus.under_review
    await db.commit()
    return ApplicationStatusOut(status=review.status, feedback=review.feedback, reviewed_at=review.reviewed_at)


@router.post("/application/reopen", response_model=ApplicationStatusOut)
async def reopen_application(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    review = await _get_review(db, current_user.id)
    if review.status != ApplicationStatus.rejected:
        raise HTTPException(status_code=400, detail="Only a rejected application can be reopened")
    review.status = ApplicationStatus.in_progress
    await db.commit()
    return ApplicationStatusOut(status=review.status, feedback=review.feedback, reviewed_at=review.reviewed_at)


@router.post("/presentation/submit", response_model=ApplicationStatusOut)
async def submit_presentation(
    body: PresentationSubmit, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)
):
    review = await _get_review(db, current_user.id)
    if review.status != ApplicationStatus.phase_1_approved:
        raise HTTPException(status_code=400, detail="Phase 2 is only open after Phase 1 approval")

    existing = (await db.execute(
        select(PresentationSubmission).where(PresentationSubmission.user_id == current_user.id)
    )).scalars().first()
    if existing:
        existing.video_link = body.video_link
    else:
        db.add(PresentationSubmission(user_id=current_user.id, video_link=body.video_link))

    review.status = ApplicationStatus.under_review
    await db.commit()
    return ApplicationStatusOut(status=review.status, feedback=review.feedback, reviewed_at=review.reviewed_at,
                                 presentation_video_link=body.video_link)


@router.get("/status", response_model=ApplicationStatusOut)
async def get_status(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_applicant)):
    review = await _get_review(db, current_user.id)
    presentation = (await db.execute(
        select(PresentationSubmission).where(PresentationSubmission.user_id == current_user.id)
    )).scalars().first()
    return ApplicationStatusOut(
        status=review.status, feedback=review.feedback, reviewed_at=review.reviewed_at,
        presentation_video_link=presentation.video_link if presentation else None,
    )
