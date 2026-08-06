"""Functional schema tests for the LMS domain (LM1-1).

These insert real rows rather than reviewing DDL, deliberately. The R1-2
lesson from this codebase's history: two VARCHAR widths in the spec text
didn't fit their own listed enum values, and DDL review missed it — only a
functional insert caught it. Every enum value below is one the system will
genuinely store, and the round-trips pin the §2 `content` JSONB shapes.

Redis-free, HTTP-free. Just the schema.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.models.lms import (
    Course,
    CourseModule,
    Enrollment,
    ItemProgress,
    ModuleItem,
    ModuleVideo,
    ProgramCurriculum,
)
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User


# ── factories ───────────────────────────────────────────────────────────────

async def _user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="LMS Author",
        email=f"lms-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="not-a-real-hash",
        roles=["operations"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _course(db, *, author=None, title=None, **kw) -> Course:
    author = author or await _user(db)
    course = Course(
        id=uuid.uuid4(),
        title=title or f"Course {uuid.uuid4().hex[:8]}",
        created_by=author.id,
        **kw,
    )
    db.add(course)
    await db.flush()
    return course


async def _module(db, course, title=None, position=1) -> CourseModule:
    module = CourseModule(
        id=uuid.uuid4(),
        course_id=course.id,
        title=title or f"Module {uuid.uuid4().hex[:8]}",
        position=position,
    )
    db.add(module)
    await db.flush()
    return module


async def _item(db, module, *, position=1, kind="text", **kw) -> ModuleItem:
    item = ModuleItem(
        id=uuid.uuid4(),
        module_id=module.id,
        position=position,
        kind=kind,
        **kw,
    )
    db.add(item)
    await db.flush()
    return item


async def _program(db, code=None) -> Program:
    program = Program(
        id=uuid.uuid4(),
        code=code or f"P-{uuid.uuid4().hex[:8]}",
        name="Test Program",
        program_type="workshop",
        pricing_model="free",
        active=True,
    )
    db.add(program)
    await db.flush()
    return program


async def _registration(db, cohort=None) -> Registration:
    contact = Contact(id=uuid.uuid4(), full_name="Registrant", contact_roles=["student"])
    db.add(contact)
    await db.flush()
    cohort = cohort or await _cohort(db)
    reg = Registration(
        id=uuid.uuid4(),
        contact_id=contact.id,
        cohort_id=cohort.id,
        ticket_token=uuid.uuid4().hex * 2,  # 64 chars, the max
        registered_via="desk",
    )
    db.add(reg)
    await db.flush()
    return reg


async def _cohort(db, program=None) -> Cohort:
    program = program or await _program(db)
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Cohort", status="planned")
    db.add(cohort)
    await db.flush()
    return cohort


# ── every table takes a real row ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_course_tree_with_video_state(db):
    """The whole authored path in one go: course -> module -> items -> video."""
    author = await _user(db)
    course = await _course(db, author=author, title="CubeSat Basics")
    module = await _module(db, course, position=1)

    db.add_all([
        ModuleItem(
            id=uuid.uuid4(), module_id=module.id, position=1, kind="text",
            title="Welcome", content={"body": "Hello!"},
        ),
        ModuleItem(
            id=uuid.uuid4(), module_id=module.id, position=2, kind="quiz",
            is_required=True, content={"pass_threshold": 70, "questions": []},
        ),
    ])
    await db.flush()

    video_item = await _item(db, module, position=3, kind="video", content={})
    video = ModuleVideo(
        id=uuid.uuid4(), item_id=video_item.id,
        source_bucket="lms-uploads", source_path="courses/cubesat/intro.mp4",
    )
    db.add(video)
    await db.flush()

    items = (await db.execute(select(ModuleItem).where(ModuleItem.module_id == module.id))).scalars().all()
    assert {i.position for i in items} == {1, 2, 3}
    assert course.kind == "course"              # server default
    assert course.is_published is False         # server default
    assert video.transcode_status == "pending"  # server default
    assert video.playlist_path is None


@pytest.mark.asyncio
async def test_curriculum_binding_and_enrollment_and_progress(db):
    """The whole student path: program -> curriculum -> enrollment -> progress."""
    author = await _user(db)
    program = await _program(db)
    course = await _course(db, author=author)
    db.add(ProgramCurriculum(
        id=uuid.uuid4(), program_id=program.id, course_id=course.id, position=1,
    ))
    await db.flush()

    student = await _user(db)
    student.roles = ["student"]
    await db.flush()
    db.add(Enrollment(
        id=uuid.uuid4(), user_id=student.id, course_id=course.id,
        source="ops", program_id=program.id,
    ))
    await db.flush()

    module = await _module(db, course)
    item = await _item(db, module, kind="text")
    db.add(ItemProgress(
        id=uuid.uuid4(), user_id=student.id, item_id=item.id,
        status="completed", completed_at=datetime.now(timezone.utc),
    ))
    await db.flush()

    progress = (await db.execute(select(ItemProgress).where(ItemProgress.user_id == student.id))).scalars().all()
    assert len(progress) == 1
    assert progress[0].best_score is None
    assert progress[0].quiz_attempts == 0       # server default


# ── content shapes round-trip (§2) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_content_shapes_round_trip(db):
    """Each §2 content shape survives insert + select byte-for-byte."""
    author = await _user(db)
    course = await _course(db, author=author)
    module = await _module(db, course)

    text_content = {"body": "Mars is the fourth planet. Its gravity is about 38% of Earth's."}
    quiz_content = {
        "pass_threshold": 70,
        "questions": [
            {
                "prompt": "What is the fourth planet from the Sun?",
                "explanation": "Mars orbits just after Earth.",
                "options": [
                    {"text": "Venus", "is_correct": False},
                    {"text": "Mars", "is_correct": True},
                ],
            }
        ],
    }
    flashcards_content = {
        "title": "Key terms",
        "cards": [
            {"term": "Orbit", "definition": "The curved path a body follows around another."},
        ],
    }
    video_content = {}

    shapes = {
        "text": text_content,
        "quiz": quiz_content,
        "flashcards": flashcards_content,
        "video": video_content,
    }
    for position, (kind, content) in enumerate(shapes.items(), start=1):
        db.add(ModuleItem(
            id=uuid.uuid4(), module_id=module.id, position=position,
            kind=kind, content=content,
        ))
    await db.flush()

    stored = (await db.execute(
        select(ModuleItem).where(ModuleItem.module_id == module.id).order_by(ModuleItem.position)
    )).scalars().all()
    assert {i.kind: i.content for i in stored} == shapes


@pytest.mark.asyncio
async def test_content_defaults_to_empty_object(db):
    author = await _user(db)
    course = await _course(db, author=author)
    module = await _module(db, course)
    item = ModuleItem(id=uuid.uuid4(), module_id=module.id, position=1, kind="text")
    db.add(item)
    await db.flush()
    assert item.content == {}


# ── uniqueness ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_module_position_is_unique_per_course(db):
    author = await _user(db)
    course = await _course(db, author=author)
    await _module(db, course, position=1)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await _module(db, course, position=1)


@pytest.mark.asyncio
async def test_item_position_is_unique_per_module(db):
    author = await _user(db)
    course = await _course(db, author=author)
    module = await _module(db, course)
    await _item(db, module, position=1)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await _item(db, module, position=1)


@pytest.mark.asyncio
async def test_one_enrollment_per_user_and_course(db):
    author = await _user(db)
    course = await _course(db, author=author)
    student = await _user(db)
    student.roles = ["student"]
    await db.flush()
    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=course.id))
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=course.id))
            await db.flush()


@pytest.mark.asyncio
async def test_one_progress_row_per_user_and_item(db):
    author = await _user(db)
    course = await _course(db, author=author)
    module = await _module(db, course)
    item = await _item(db, module)
    student = await _user(db)
    student.roles = ["student"]
    await db.flush()
    db.add(ItemProgress(id=uuid.uuid4(), user_id=student.id, item_id=item.id))
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(ItemProgress(id=uuid.uuid4(), user_id=student.id, item_id=item.id))
            await db.flush()


@pytest.mark.asyncio
async def test_curriculum_cannot_list_a_course_twice(db):
    author = await _user(db)
    program = await _program(db)
    course = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=course.id, position=1))
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=course.id, position=2))
            await db.flush()


@pytest.mark.asyncio
async def test_curriculum_position_is_unique_per_program(db):
    author = await _user(db)
    program = await _program(db)
    a = await _course(db, author=author)
    b = await _course(db, author=author)
    db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=a.id, position=1))
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(ProgramCurriculum(id=uuid.uuid4(), program_id=program.id, course_id=b.id, position=1))
            await db.flush()


@pytest.mark.asyncio
async def test_video_state_is_one_row_per_item(db):
    author = await _user(db)
    course = await _course(db, author=author)
    module = await _module(db, course)
    item = await _item(db, module, kind="video")
    db.add(ModuleVideo(
        id=uuid.uuid4(), item_id=item.id,
        source_bucket="b", source_path="p.mp4",
    ))
    await db.flush()
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            db.add(ModuleVideo(
                id=uuid.uuid4(), item_id=item.id,
                source_bucket="b", source_path="p2.mp4",
            ))
            await db.flush()


# ── delete behaviour: the decisions worth pinning ───────────────────────────

@pytest.mark.asyncio
async def test_deleting_a_student_removes_enrollments_and_progress(db):
    """The inverse of inventory custody: progress is worthless without the
    student, so enrollments + progress CASCADE on user delete (§2 note)."""
    author = await _user(db)
    course = await _course(db, author=author)
    module = await _module(db, course)
    item = await _item(db, module)
    student = await _user(db)
    student.roles = ["student"]
    await db.flush()
    db.add(Enrollment(id=uuid.uuid4(), user_id=student.id, course_id=course.id))
    db.add(ItemProgress(id=uuid.uuid4(), user_id=student.id, item_id=item.id, status="completed"))
    await db.flush()

    await db.execute(delete(User).where(User.id == student.id))
    await db.flush()

    enrollments = (await db.execute(select(Enrollment).where(Enrollment.user_id == student.id))).scalars().all()
    progress = (await db.execute(select(ItemProgress).where(ItemProgress.user_id == student.id))).scalars().all()
    assert enrollments == []
    assert progress == []
    # the course itself survives — it was never the student's
    assert (await db.execute(select(Course).where(Course.id == course.id))).scalars().first() is not None


@pytest.mark.asyncio
async def test_deleting_a_course_removes_its_tree(db):
    author = await _user(db)
    course = await _course(db, author=author)
    module = await _module(db, course)
    item = await _item(db, module)
    video = ModuleVideo(id=uuid.uuid4(), item_id=item.id, source_bucket="b", source_path="p.mp4")
    db.add(video)
    await db.flush()

    await db.execute(delete(Course).where(Course.id == course.id))
    await db.flush()

    modules = (await db.execute(select(CourseModule).where(CourseModule.course_id == course.id))).scalars().all()
    items = (await db.execute(select(ModuleItem).where(ModuleItem.module_id == module.id))).scalars().all()
    videos = (await db.execute(select(ModuleVideo).where(ModuleVideo.item_id == item.id))).scalars().all()
    assert modules == [] and items == [] and videos == []


@pytest.mark.asyncio
async def test_course_author_cannot_be_deleted_while_courses_exist(db):
    """courses.created_by is RESTRICT — a course with no author behind it is
    unmaintainable, same reasoning as movements.created_by."""
    author = await _user(db)
    await _course(db, author=author)
    with pytest.raises(IntegrityError):
        async with db.begin_nested():
            await db.execute(delete(User).where(User.id == author.id))
            await db.flush()


@pytest.mark.asyncio
async def test_deleting_a_program_keeps_the_enrollment(db):
    """enrollments.program_id is provenance, not membership: when the program
    row dies, the enrollment survives (source history intact) with SET NULL."""
    author = await _user(db)
    program = await _program(db)
    course = await _course(db, author=author)
    student = await _user(db)
    student.roles = ["student"]
    await db.flush()
    enrollment = Enrollment(
        id=uuid.uuid4(), user_id=student.id, course_id=course.id,
        source="ops", program_id=program.id,
    )
    db.add(enrollment)
    await db.flush()

    await db.execute(delete(Program).where(Program.id == program.id))
    await db.flush()
    await db.refresh(enrollment)

    assert enrollment.program_id is None
    assert enrollment.status == "active"
    assert enrollment.user_id == student.id


@pytest.mark.asyncio
async def test_deleting_a_registration_keeps_the_enrollment(db):
    """Same provenance logic as program_id: SET NULL, never CASCADE."""
    author = await _user(db)
    course = await _course(db, author=author)
    student = await _user(db)
    student.roles = ["student"]
    await db.flush()
    cohort = await _cohort(db)
    registration = await _registration(db, cohort)
    enrollment = Enrollment(
        id=uuid.uuid4(), user_id=student.id, course_id=course.id,
        source="registration", registration_id=registration.id,
    )
    db.add(enrollment)
    await db.flush()

    await db.execute(delete(Registration).where(Registration.id == registration.id))
    await db.flush()
    await db.refresh(enrollment)

    assert enrollment.registration_id is None
    assert enrollment.status == "active"


# ── column widths actually fit the values we intend to store ────────────────

@pytest.mark.asyncio
async def test_real_world_values_fit_their_columns(db):
    """The R1-2 lesson: widths that look fine in DDL review can fail on the
    first real insert. Every value here is one this system will genuinely
    store — the longest enum member per column."""
    author = await _user(db)
    # kind='mission' (7) fits VARCHAR(12); title max length
    course = await _course(db, author=author, title="M" * 128, kind="mission", is_published=True)
    module = await _module(db, course, title="M" * 128)
    # kind='flashcards' (10) fits VARCHAR(10)
    item = await _item(db, module, kind="flashcards")
    db.add(ModuleVideo(
        id=uuid.uuid4(), item_id=item.id,
        source_bucket="B" * 64,
        source_path="P" * 512,
        playlist_path="P" * 512,
        key_path="K" * 512,
        # 'processing' (10) fits VARCHAR(12)
        transcode_status="processing",
    ))
    db.add(Enrollment(
        id=uuid.uuid4(), user_id=author.id, course_id=course.id,
        # 'registration' (12) fits VARCHAR(12) exactly
        source="registration",
        # 'inactive' (8) fits VARCHAR(10)
        status="inactive",
    ))
    db.add(ItemProgress(
        id=uuid.uuid4(), user_id=author.id, item_id=item.id,
        # 'not_started' (11) fits VARCHAR(12)
        status="not_started",
        best_score=99.99,
        quiz_attempts=3,
    ))
    await db.flush()
