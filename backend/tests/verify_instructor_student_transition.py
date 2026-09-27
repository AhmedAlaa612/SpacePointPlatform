"""Verification test for instructor/staff transition to student and card number handling (2026-09-27)."""

import asyncio
import os
import sys
import uuid
import secrets

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:67500@localhost:5433/spacepoint_dev"

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.security import get_password_hash
from app.models.enums import UserRole
from app.models.user import User
from app.models.spine.contact import Contact
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.services.documents.id_card import ensure_card_number
from app.services.lms.ops_integration import get_or_create_student_account, sync_registration_lms
from app.services.sessions.registration import register


async def main():
    engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as db:
        print("Testing Instructor -> Student transition card_number collision fix...")

        # 1. Create an existing student user who holds a student card number
        student_email = f"real_student_{uuid.uuid4().hex[:6]}@example.com"
        student_user = User(
            id=uuid.uuid4(),
            full_name="Existing Student",
            email=student_email,
            password_hash=get_password_hash("pass123"),
            roles=[UserRole.student],
            status="active",
        )
        db.add(student_user)
        await db.flush()
        # Allocate student card number
        student_card_no = await ensure_card_number(db, student_user)
        print(f"Existing student allocated student card #{student_card_no}")

        # 2. Create an instructor user who had the SAME card number (simulating collision across pools)
        instructor_email = f"instructor_{uuid.uuid4().hex[:6]}@example.com"
        instructor_user = User(
            id=uuid.uuid4(),
            full_name="Instructor John",
            email=instructor_email,
            password_hash=get_password_hash("pass123"),
            roles=[UserRole.instructor],
            status="active",
            card_number=student_card_no,  # Identical card number in staff pool!
        )
        db.add(instructor_user)
        await db.flush()
        await db.commit()
        print(f"Created instructor user with overlapping card #{instructor_user.card_number} in staff pool")

        # 3. Create a contact for this instructor registering for a cohort
        contact = Contact(
            id=uuid.uuid4(),
            full_name="Instructor John",
            email=instructor_email,
            contact_roles=["student"],
        )
        db.add(contact)
        await db.flush()

        # 4. Now call get_or_create_student_account (the function that caused the bug)
        reused_user, was_created = await get_or_create_student_account(db, contact.id)
        assert reused_user is not None, "User should be resolved and reused"
        assert was_created is False, "Account was reused, not created from scratch"
        assert "student" in reused_user.role_values, "Student role was added"
        assert "instructor" in reused_user.role_values, "Instructor role was preserved"
        assert reused_user.card_number != student_card_no or student_card_no is None, \
            "Card number must have been reallocated so it does not collide with existing student"
        print(f"Reused user now has roles={reused_user.role_values} and NEW student card #{reused_user.card_number}")

        # 5. Flush and commit to ensure PostgreSQL's idx_users_card_number_student constraint passes
        await db.commit()
        print("db.commit() SUCCEEDED without unique constraint violation!")

        # 6. Test full sync_registration_lms in a cohort
        # Find or create a program and cohort
        program = (await db.execute(select(Program).limit(1))).scalars().first()
        if not program:
            program = Program(id=uuid.uuid4(), name="Test Program", code="TP")
            db.add(program)
            await db.flush()

        cohort = (await db.execute(select(Cohort).where(Cohort.program_id == program.id).limit(1))).scalars().first()
        if not cohort:
            cohort = Cohort(
                id=uuid.uuid4(),
                program_id=program.id,
                name="Test Cohort",
                status="draft",
            )
            db.add(cohort)
            await db.flush()

        reg = await register(
            db,
            contact_id=contact.id,
            cohort_id=cohort.id,
            registered_via="desk",
        )
        await db.flush()

        lms_user = await sync_registration_lms(
            db,
            registration=reg,
            cohort=cohort,
            create_account=True,
            send_welcome_email=False,
        )
        assert lms_user is not None, "sync_registration_lms should return the user"
        await db.commit()
        print("sync_registration_lms and registration commit SUCCEEDED!")

        # Clean up test rows
        await db.delete(reg)
        await db.delete(instructor_user)
        await db.delete(student_user)
        await db.delete(contact)
        await db.commit()
        print("Cleanup completed. ALL TESTS PASSED 100%!")


if __name__ == "__main__":
    asyncio.run(main())
