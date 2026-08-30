import asyncio
import sys
import uuid
from pathlib import Path

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select

from app.db.email_template_defaults import EMAIL_TEMPLATE_DEFAULTS
from app.db.session import AsyncSessionLocal
from app.models.email_template import EmailTemplate


async def seed():
    async with AsyncSessionLocal() as session:
        print("Seeding email templates...")
        for t in EMAIL_TEMPLATE_DEFAULTS:
            existing = (await session.execute(
                select(EmailTemplate).where(EmailTemplate.key == t["key"])
            )).scalars().first()
            if existing:
                print(f"Template already exists: {t['key']}, skipping.")
                continue
            print(f"Adding template: {t['name']} ({t['key']})")
            session.add(EmailTemplate(
                id=uuid.uuid4(),
                key=t["key"],
                name=t["name"],
                category=t["category"],
                description=t["description"],
                subject=t["subject"],
                body_html=t["body_html"],
                placeholders=t["placeholders"],
                attachment_labels=t["attachment_labels"],
                is_internal=t["is_internal"],
            ))
        await session.commit()
        print("Seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
