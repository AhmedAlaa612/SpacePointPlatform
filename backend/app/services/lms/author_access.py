"""LMS author access control helpers.

Controls permissions and scoping for users holding the `lms_author` role.
Admin, operations, and facilitator retain platform-wide access (scope_all=True, can_publish=True).
For `lms_author`, access depends on their `LmsAuthorProfile` row:
- `scope_all`: whether they can view and edit courses/paths created by other users.
- `can_publish`: whether they can directly publish/unpublish courses and learning paths.
"""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.author_profile import LmsAuthorProfile
from app.models.lms.course import Course, CourseModule, ModuleItem, VideoCheckpoint
from app.models.lms.learning_path import LearningPath
from app.models.user import User


async def get_author_permissions(db: AsyncSession, user: User) -> tuple[bool, bool]:
    """Returns (can_publish, scope_all) for the given user.

    Admin, operations, and facilitator are treated as full-access (True, True).
    If the user has 'lms_author', reads their LmsAuthorProfile.
    Otherwise defaults to (False, False).
    """
    if any(r in user.role_values for r in ("admin", "operations", "facilitator")):
        return (True, True)
    if "lms_author" in user.role_values:
        profile = await db.get(LmsAuthorProfile, user.id)
        if profile:
            return (profile.can_publish, profile.scope_all)
        return (False, False)
    return (False, False)


async def is_course_author_or_staff(db: AsyncSession, user: User, course: Course) -> bool:
    """Returns True if the user has staff privileges or authorship over this course."""
    if any(r in user.role_values for r in ("admin", "operations", "facilitator")):
        return True
    if "lms_author" in user.role_values:
        _, scope_all = await get_author_permissions(db, user)
        return scope_all or course.created_by == user.id
    return False


async def check_course_access(db: AsyncSession, user: User, course: Course) -> None:
    """Raises 404 if the author does not have scope over this course."""
    _, scope_all = await get_author_permissions(db, user)
    if not scope_all and course.created_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Course not found")


async def check_course_publish_access(db: AsyncSession, user: User, course: Course) -> None:
    """Checks course scope and raises 403 if the user cannot publish directly."""
    await check_course_access(db, user, course)
    can_publish, _ = await get_author_permissions(db, user)
    if not can_publish:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You do not have direct publishing permissions. Please contact an administrator to review and publish this course.",
        )


async def check_module_access(db: AsyncSession, user: User, module: CourseModule) -> Course:
    """Finds the module's course and verifies scope access. Returns the Course."""
    course = await db.get(Course, module.course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Module not found")
    await check_course_access(db, user, course)
    return course


async def check_item_access(db: AsyncSession, user: User, item: ModuleItem) -> tuple[CourseModule, Course]:
    """Finds the item's module and course, verifying scope access. Returns (module, course)."""
    module = await db.get(CourseModule, item.module_id)
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Item not found")
    course = await check_module_access(db, user, module)
    return module, course


async def check_checkpoint_access(
    db: AsyncSession, user: User, checkpoint: VideoCheckpoint
) -> tuple[ModuleItem, CourseModule, Course]:
    """Finds the checkpoint's item, module, and course, verifying scope access."""
    item = await db.get(ModuleItem, checkpoint.item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Checkpoint not found")
    module, course = await check_item_access(db, user, item)
    return item, module, course


async def check_learning_path_access(db: AsyncSession, user: User, path: LearningPath) -> None:
    """Raises 404 if the author does not have scope over this learning path."""
    _, scope_all = await get_author_permissions(db, user)
    if not scope_all and path.created_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Learning path not found")


async def check_learning_path_publish_access(db: AsyncSession, user: User, path: LearningPath) -> None:
    """Checks path scope and raises 403 if the user cannot publish directly."""
    await check_learning_path_access(db, user, path)
    can_publish, _ = await get_author_permissions(db, user)
    if not can_publish:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail="You do not have direct publishing permissions. Please contact an administrator to review and publish this learning path.",
        )


async def check_invite_code_access(db: AsyncSession, user: User, code: InvitationCode) -> None:
    """Raises 404 if the author does not have scope over this invite code."""
    _, scope_all = await get_author_permissions(db, user)
    if not scope_all and code.created_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Invite code not found")

