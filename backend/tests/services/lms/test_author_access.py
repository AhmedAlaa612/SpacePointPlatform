import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import HTTPException

from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.author_profile import LmsAuthorProfile
from app.models.lms.course import Course, CourseModule, ModuleItem, VideoCheckpoint
from app.models.lms.learning_path import LearningPath
from app.services.lms.author_access import (
    check_checkpoint_access,
    check_course_access,
    check_course_publish_access,
    check_invite_code_access,
    check_item_access,
    check_learning_path_access,
    check_learning_path_publish_access,
    check_module_access,
    get_author_permissions,
    is_course_author_or_staff,
)


def make_mock_user(roles: list[str], user_id: uuid.UUID | None = None):
    user = MagicMock()
    user.id = user_id or uuid.uuid4()
    user.role_values = roles
    return user


@pytest.mark.asyncio
async def test_get_author_permissions_admin_and_staff():
    db = AsyncMock()
    for role in ("admin", "operations", "facilitator"):
        user = make_mock_user([role])
        can_publish, scope_all = await get_author_permissions(db, user)
        assert can_publish is True
        assert scope_all is True


@pytest.mark.asyncio
async def test_get_author_permissions_lms_author():
    db = AsyncMock()
    user = make_mock_user(["lms_author"])

    # No profile exists
    db.get.return_value = None
    can_publish, scope_all = await get_author_permissions(db, user)
    assert can_publish is False
    assert scope_all is False

    # Profile with draft-only (can_publish=False) and own-content (scope_all=False)
    profile = LmsAuthorProfile(user_id=user.id, can_publish=False, scope_all=False)
    db.get.return_value = profile
    can_publish, scope_all = await get_author_permissions(db, user)
    assert can_publish is False
    assert scope_all is False

    # Profile with direct-publish and all-content
    profile.can_publish = True
    profile.scope_all = True
    db.get.return_value = profile
    can_publish, scope_all = await get_author_permissions(db, user)
    assert can_publish is True
    assert scope_all is True


@pytest.mark.asyncio
async def test_check_course_access():
    db = AsyncMock()
    author_id = uuid.uuid4()
    other_id = uuid.uuid4()
    author = make_mock_user(["lms_author"], user_id=author_id)

    # Scoped author (scope_all=False)
    profile = LmsAuthorProfile(user_id=author_id, can_publish=False, scope_all=False)
    db.get.return_value = profile

    own_course = Course(id=uuid.uuid4(), created_by=author_id, title="Own Course")
    other_course = Course(id=uuid.uuid4(), created_by=other_id, title="Other Course")

    # Own course should pass
    await check_course_access(db, author, own_course)

    # Other course should raise 404
    with pytest.raises(HTTPException) as exc_info:
        await check_course_access(db, author, other_course)
    assert exc_info.value.status_code == 404

    # Now grant scope_all=True
    profile.scope_all = True
    await check_course_access(db, author, other_course)


@pytest.mark.asyncio
async def test_check_course_publish_access():
    db = AsyncMock()
    author_id = uuid.uuid4()
    author = make_mock_user(["lms_author"], user_id=author_id)
    profile = LmsAuthorProfile(user_id=author_id, can_publish=False, scope_all=False)
    db.get.return_value = profile

    own_course = Course(id=uuid.uuid4(), created_by=author_id, title="Own Course")

    # cannot publish -> 403
    with pytest.raises(HTTPException) as exc_info:
        await check_course_publish_access(db, author, own_course)
    assert exc_info.value.status_code == 403

    # grant can_publish -> passes
    profile.can_publish = True
    await check_course_publish_access(db, author, own_course)


@pytest.mark.asyncio
async def test_check_module_and_item_access():
    author_id = uuid.uuid4()
    other_id = uuid.uuid4()
    author = make_mock_user(["lms_author"], user_id=author_id)
    profile = LmsAuthorProfile(user_id=author_id, can_publish=False, scope_all=False)

    course_id = uuid.uuid4()
    own_course = Course(id=course_id, created_by=author_id, title="Own Course")
    module_id = uuid.uuid4()
    module = CourseModule(id=module_id, course_id=course_id, title="Module 1")
    item_id = uuid.uuid4()
    item = ModuleItem(id=item_id, module_id=module_id, title="Lesson 1")
    chk_id = uuid.uuid4()
    checkpoint = VideoCheckpoint(id=chk_id, item_id=item_id)

    db = AsyncMock()

    async def mock_get(model, pk):
        if model is LmsAuthorProfile and pk == author_id:
            return profile
        if model is Course and pk == course_id:
            return own_course
        if model is CourseModule and pk == module_id:
            return module
        if model is ModuleItem and pk == item_id:
            return item
        if model is VideoCheckpoint and pk == chk_id:
            return checkpoint
        return None

    db.get.side_effect = mock_get

    # Accessing module, item, and checkpoint should all succeed for own course
    res_course = await check_module_access(db, author, module)
    assert res_course.id == course_id

    res_mod, res_crs = await check_item_access(db, author, item)
    assert res_mod.id == module_id
    assert res_crs.id == course_id

    res_itm, res_mod2, res_crs2 = await check_checkpoint_access(db, author, checkpoint)
    assert res_itm.id == item_id

    # If course belongs to other user and author has scope_all=False -> 404
    own_course.created_by = other_id
    with pytest.raises(HTTPException) as exc_info:
        await check_item_access(db, author, item)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_check_learning_path_access_and_publish():
    db = AsyncMock()
    author_id = uuid.uuid4()
    other_id = uuid.uuid4()
    author = make_mock_user(["lms_author"], user_id=author_id)
    profile = LmsAuthorProfile(user_id=author_id, can_publish=False, scope_all=False)
    db.get.return_value = profile

    own_path = LearningPath(id=uuid.uuid4(), created_by=author_id, title="Own Path")
    other_path = LearningPath(id=uuid.uuid4(), created_by=other_id, title="Other Path")

    # Own path access succeeds
    await check_learning_path_access(db, author, own_path)

    # Other path access fails with 404
    with pytest.raises(HTTPException) as exc_info:
        await check_learning_path_access(db, author, other_path)
    assert exc_info.value.status_code == 404

    # Own path publish fails with 403 when can_publish=False
    with pytest.raises(HTTPException) as exc_info:
        await check_learning_path_publish_access(db, author, own_path)
    assert exc_info.value.status_code == 403

    # Can publish passes when can_publish=True
    profile.can_publish = True
    await check_learning_path_publish_access(db, author, own_path)


@pytest.mark.asyncio
async def test_check_invite_code_access():
    db = AsyncMock()
    author_id = uuid.uuid4()
    other_id = uuid.uuid4()
    author = make_mock_user(["lms_author"], user_id=author_id)
    profile = LmsAuthorProfile(user_id=author_id, can_publish=False, scope_all=False)
    db.get.return_value = profile

    own_code = InvitationCode(id=uuid.uuid4(), created_by=author_id, code="AUTH123")
    other_code = InvitationCode(id=uuid.uuid4(), created_by=other_id, code="HELLO")
    legacy_code = InvitationCode(id=uuid.uuid4(), created_by=None, code="LEGACY")

    # Own code succeeds
    await check_invite_code_access(db, author, own_code)

    # Other's code raises 404
    with pytest.raises(HTTPException) as exc_info:
        await check_invite_code_access(db, author, other_code)
    assert exc_info.value.status_code == 404

    # Legacy code without created_by raises 404 for scoped author
    with pytest.raises(HTTPException) as exc_info:
        await check_invite_code_access(db, author, legacy_code)
    assert exc_info.value.status_code == 404

    # When author has scope_all=True, can access all codes
    profile.scope_all = True
    await check_invite_code_access(db, author, other_code)
    await check_invite_code_access(db, author, legacy_code)


@pytest.mark.asyncio
async def test_author_assigned_access_scoping():
    db = AsyncMock()
    author_id = uuid.uuid4()
    author = make_mock_user(["lms_author"], user_id=author_id)
    profile = LmsAuthorProfile(user_id=author_id, can_publish=False, scope_all=False)
    db.get.return_value = profile

    _, scope_all = await get_author_permissions(db, author)
    assert scope_all is False

    profile.scope_all = True
    _, scope_all = await get_author_permissions(db, author)
    assert scope_all is True


@pytest.mark.asyncio
async def test_is_course_author_or_staff():
    db = AsyncMock()
    author_id = uuid.uuid4()
    other_id = uuid.uuid4()

    course = Course(id=uuid.uuid4(), created_by=author_id, title="Test Course")

    # Admin, operations, facilitator are always staff
    for role in ("admin", "operations", "facilitator"):
        user = make_mock_user([role])
        assert await is_course_author_or_staff(db, user, course) is True

    # LMS author with own course
    author = make_mock_user(["lms_author"], user_id=author_id)
    profile = LmsAuthorProfile(user_id=author_id, can_publish=False, scope_all=False)
    db.get.return_value = profile
    assert await is_course_author_or_staff(db, author, course) is True

    # LMS author with other course when scope_all=False
    other_author = make_mock_user(["lms_author"], user_id=other_id)
    other_profile = LmsAuthorProfile(user_id=other_id, can_publish=False, scope_all=False)
    db.get.return_value = other_profile
    assert await is_course_author_or_staff(db, other_author, course) is False

    # LMS author with other course when scope_all=True
    other_profile.scope_all = True
    assert await is_course_author_or_staff(db, other_author, course) is True

    # Plain student
    student = make_mock_user(["student"])
    assert await is_course_author_or_staff(db, student, course) is False

