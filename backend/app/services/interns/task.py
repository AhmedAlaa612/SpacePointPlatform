from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from fastapi import HTTPException, status
from uuid import UUID
from datetime import datetime, timezone

from app.models.interns.task import Task
from app.models.interns.module import Module
from app.models.interns.epic import Epic
from app.models.interns.submission import TaskSubmission
from app.models.interns.team import Team
from app.schemas.interns.task import TaskCreate, TaskUpdate, TaskAssign, TaskStatusUpdate
from app.schemas.interns.submission import TaskSubmissionCreate, TaskSubmissionReview
from app.models.enums import SubmissionStatus, WorkStatus
from app.services.user import get_user_by_id
from app.services import notification as notification_service


def _task_options():
    return [
        selectinload(Task.assignees),
        selectinload(Task.submissions).selectinload(TaskSubmission.submitter),
        joinedload(Task.module).joinedload(Module.epic),
    ]


async def create_task(db: AsyncSession, module_id: UUID, task_in: TaskCreate, user_id: UUID) -> Task:
    task = Task(
        module_id=module_id,
        title=task_in.title,
        description=task_in.description,
        due_date=task_in.due_date,
        expected_time=task_in.expected_time,
        created_by=user_id,
    )
    db.add(task)
    await db.commit()
    return await get_task_by_id(db, task.id)


async def get_task_by_id(db: AsyncSession, task_id: UUID) -> Task:
    result = await db.execute(
        select(Task).where(Task.id == task_id).options(*_task_options())
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


async def get_all_tasks(db: AsyncSession):
    result = await db.execute(select(Task).options(*_task_options()))
    return result.scalars().all()


async def get_tasks_by_module(db: AsyncSession, module_id: UUID):
    result = await db.execute(
        select(Task).where(Task.module_id == module_id).options(*_task_options())
    )
    return result.scalars().all()


async def get_tasks_by_team(db: AsyncSession, team_id: UUID):
    result = await db.execute(
        select(Task)
        .join(Module, Task.module_id == Module.id)
        .join(Epic,   Module.epic_id == Epic.id)
        .where(Epic.team_id == team_id)
        .options(*_task_options())
    )
    return result.scalars().all()


async def get_tasks_assigned_to(db: AsyncSession, user_id: UUID):
    result = await db.execute(
        select(Task)
        .filter(Task.assignees.any(id=user_id))
        .options(*_task_options())
    )
    return result.scalars().all()


async def update_task(db: AsyncSession, task_id: UUID, task_in: TaskUpdate) -> Task:
    task = await get_task_by_id(db, task_id)
    for field, value in task_in.dict(exclude_unset=True).items():
        setattr(task, field, value)
    await db.commit()
    return await get_task_by_id(db, task_id)


async def update_task_status(db: AsyncSession, task_id: UUID, status_in: TaskStatusUpdate) -> Task:
    task = await get_task_by_id(db, task_id)
    task.status = status_in.status
    await db.commit()
    return await get_task_by_id(db, task_id)


async def delete_task(db: AsyncSession, task_id: UUID):
    task = await get_task_by_id(db, task_id)
    await db.delete(task)
    await db.commit()
    return {"detail": "Task deleted"}


async def assign_task(db: AsyncSession, task_id: UUID, assign_in: TaskAssign) -> Task:
    task = await get_task_by_id(db, task_id)
    for uid in assign_in.user_ids:
        user = await get_user_by_id(db, uid)
        if user not in task.assignees:
            task.assignees.append(user)
            await notification_service.create_notification(
                db, uid,
                "New task assigned",
                f'You\'ve been assigned to: "{task.title}"',
            )
    await db.commit()
    return await get_task_by_id(db, task_id)


async def unassign_task(db: AsyncSession, task_id: UUID, user_id: UUID) -> Task:
    task = await get_task_by_id(db, task_id)
    task.assignees = [u for u in task.assignees if str(u.id) != str(user_id)]
    await db.commit()
    return await get_task_by_id(db, task_id)


async def submit_task_work(
    db: AsyncSession, task_id: UUID, submit_in: TaskSubmissionCreate, user_id: UUID
) -> TaskSubmission:
    task = await get_task_by_id(db, task_id)

    submission = TaskSubmission(
        task_id=task_id,
        submitted_by=user_id,
        link=submit_in.link,
        note=submit_in.note,
    )
    db.add(submission)

    if submit_in.actual_time is not None:
        task.actual_time = submit_in.actual_time

    task.status = WorkStatus.done

    # Notify the team leader
    module_result = await db.execute(select(Module).where(Module.id == task.module_id))
    module = module_result.scalars().first()
    if module:
        epic_result = await db.execute(select(Epic).where(Epic.id == module.epic_id))
        epic = epic_result.scalars().first()
        if epic:
            team_result = await db.execute(select(Team).where(Team.id == epic.team_id))
            team = team_result.scalars().first()
            if team and team.leader_id:
                await notification_service.create_notification(
                    db, team.leader_id,
                    "Work submitted for review",
                    f'"{task.title}" has a new submission ready to review.',
                )

    await db.commit()
    await db.refresh(submission)

    result = await db.execute(
        select(TaskSubmission)
        .where(TaskSubmission.id == submission.id)
        .options(selectinload(TaskSubmission.submitter))
    )
    return result.scalars().first()


async def review_submission(
    db: AsyncSession, submission_id: UUID, review_in: TaskSubmissionReview
) -> TaskSubmission:
    result = await db.execute(
        select(TaskSubmission)
        .where(TaskSubmission.id == submission_id)
        .options(selectinload(TaskSubmission.submitter))
    )
    submission = result.scalars().first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    submission.score = review_in.score
    submission.review_comment = review_in.review_comment
    submission.status = SubmissionStatus.reviewed
    submission.reviewed_at = datetime.now(timezone.utc)

    await notification_service.create_notification(
        db, submission.submitted_by,
        "Submission reviewed",
        f"Your submission was reviewed â€” score: {review_in.score}",
    )

    await db.commit()
    await db.refresh(submission)
    return submission
