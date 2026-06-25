import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.db.session import get_db
from app.core.dependencies import get_current_active_user
from app.models.user import User
from app.models.ambassadors.task import AmbassadorTask
from app.schemas.ambassadors.task import TaskCreate, TaskOut, TaskStatusUpdate, TaskUpdate, AssignableUser
from app.services.points import award_points, adjust_points
from app.services.notification import create_notification as notify

logger = logging.getLogger("ambassador-tasks")
router = APIRouter(prefix="/tasks", tags=["ambassador-tasks"])

# Allowed transitions: new status → statuses it may come from.
ASSIGNEE_TRANSITIONS = {
    "accepted": {"pending"},
    "submitted": {"accepted", "edit_requested"},
}
OWNER_TRANSITIONS = {
    "approved": {"submitted"},
    "rejected": {"submitted", "approved"},
    "edit_requested": {"submitted", "approved"},
}


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    body: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    assignee = (await db.execute(select(User).where(User.id == body.assigned_to))).scalars().first()
    if not assignee:
        raise HTTPException(status_code=404, detail="Assignee not found")

    roles = current_user.role_values
    assignee_roles = assignee.role_values
    if "admin" in roles:
        if not any(r in assignee_roles for r in ("ambassador", "teacher")):
            raise HTTPException(status_code=400, detail="Admin can only assign to ambassadors or teachers")
    elif "ambassador" in roles:
        if "teacher" not in assignee_roles or assignee.invited_by_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only assign tasks to teachers you invited")
    else:
        raise HTTPException(status_code=403, detail="Not permitted to create tasks")

    task = AmbassadorTask(
        assigned_to=assignee.id,
        created_by=current_user.id,
        title=body.title,
        description=body.description,
        deadline=body.deadline,
        points_reward=body.points_reward,
        status="pending",
    )
    db.add(task)
    await notify(db, assignee.id, "New Task Assigned", f"You were assigned: {body.title}")
    await db.commit()
    await db.refresh(task)
    return task


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    view: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    roles = current_user.role_values
    if "admin" in roles and view != "created":
        q = select(AmbassadorTask).order_by(AmbassadorTask.created_at.desc())
    elif view == "created":
        q = select(AmbassadorTask).where(AmbassadorTask.created_by == current_user.id).order_by(AmbassadorTask.created_at.desc())
    else:
        q = select(AmbassadorTask).where(AmbassadorTask.assigned_to == current_user.id).order_by(AmbassadorTask.created_at.desc())
    return list((await db.execute(q)).scalars().all())


@router.get("/assignable-users", response_model=list[AssignableUser])
async def assignable_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    roles = current_user.role_values
    if "admin" in roles:
        q = select(User).where(
            User.roles.any("ambassador") | User.roles.any("teacher"),
            User.status == "active"
        ).order_by(User.full_name)
    elif "ambassador" in roles:
        q = select(User).where(
            User.roles.any("teacher"), User.invited_by_id == current_user.id, User.status == "active"
        ).order_by(User.full_name)
    else:
        return []
    return list((await db.execute(q)).scalars().all())


@router.put("/{task_id}/status", response_model=TaskOut)
async def update_task_status(
    task_id: uuid.UUID,
    body: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    task = (await db.execute(select(AmbassadorTask).where(AmbassadorTask.id == task_id))).scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    new_status = body.status
    is_assignee = task.assigned_to == current_user.id
    is_owner = task.created_by == current_user.id or "admin" in current_user.role_values

    if is_assignee and new_status in ASSIGNEE_TRANSITIONS:
        if task.status not in ASSIGNEE_TRANSITIONS[new_status]:
            raise HTTPException(status_code=400, detail=f"Can't move a '{task.status}' task to '{new_status}'")
    elif is_owner and new_status in OWNER_TRANSITIONS:
        if task.status not in OWNER_TRANSITIONS[new_status]:
            raise HTTPException(status_code=400, detail=f"Can't move a '{task.status}' task to '{new_status}'")
        if new_status == "approved" and not task.points_awarded:
            await award_points(db, task.assigned_to, task.points_reward, f"Completed task: {task.title}")
            task.points_awarded = True
        elif task.status == "approved" and task.points_awarded:
            await adjust_points(db, task.assigned_to, -task.points_reward, f"Task approval revoked: {task.title}")
            task.points_awarded = False
    else:
        raise HTTPException(status_code=403, detail="Not authorized to set this status")

    task.status = new_status
    if body.edit_notes is not None:
        task.edit_notes = body.edit_notes
    if new_status == "submitted" and body.submission is not None:
        task.submission = body.submission

    if new_status == "submitted" and task.created_by:
        await notify(db, task.created_by, "Task Submitted", f"'{task.title}' is ready for review.")
    elif new_status == "approved":
        await notify(db, task.assigned_to, "Task Approved!", f"'{task.title}' approved — {task.points_reward} points awarded.")
    elif new_status == "rejected":
        await notify(db, task.assigned_to, "Task Rejected", f"'{task.title}' was rejected.")
    elif new_status == "edit_requested":
        await notify(db, task.assigned_to, "Revision Requested", f"A revision was requested for '{task.title}'.")

    await db.commit()
    await db.refresh(task)
    return task


async def _get_editable_task(db: AsyncSession, task_id: uuid.UUID, user: User) -> AmbassadorTask:
    task = (await db.execute(select(AmbassadorTask).where(AmbassadorTask.id == task_id))).scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if "admin" not in user.role_values and task.created_by != user.id:
        raise HTTPException(status_code=403, detail="Only the task creator or an admin can do this")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def edit_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    task = await _get_editable_task(db, task_id, current_user)
    data = body.model_dump(exclude_unset=True)
    if "points_reward" in data and task.points_awarded and data["points_reward"] != task.points_reward:
        raise HTTPException(status_code=400, detail="Reward can't change after points were awarded — revoke approval first")
    for k, v in data.items():
        setattr(task, k, v)
    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}")
async def delete_task(
    task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    task = await _get_editable_task(db, task_id, current_user)
    if task.points_awarded:
        await adjust_points(db, task.assigned_to, -task.points_reward, f"Task deleted: {task.title}")
    await db.delete(task)
    await db.commit()
    return {"status": "deleted"}
