import asyncio
import sys
from pathlib import Path

# Add backend to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.db.session import AsyncSessionLocal
from app.models.document_template import DocumentTemplate
from sqlalchemy import select


DEFAULT_TEMPLATES = [
    {
        "key": "recommendation_letter",
        "name": "Recommendation Letter",
        "roles": ["intern", "instructor", "facilitator", "ambassador"],
        "body_text": (
            "{date}\n"
            "To Whom It May Concern,\n\n"
            "{name} has participated in the {role} program at SpacePoint FZC. During their tenure, they demonstrated outstanding skill, diligence, and dedication. I highly recommend them for any professional endeavors they choose to pursue.\n\n"
            "{signature}\n"
            "{signatory_name}\n"
            "{signatory_title}"
        )
    },
    {
        "key": "confirmation_letter",
        "name": "Confirmation Letter",
        "roles": ["intern", "instructor", "facilitator", "teacher", "ambassador"],
        "body_text": (
            "{date}\n"
            "To Whom It May Concern,\n\n"
            "This is to confirm that {name} is currently undertaking the {role} program at SpacePoint FZC, since {start_date}.\n\n"
            "{signature}\n"
            "{signatory_name}\n"
            "{signatory_title}"
        )
    },
    {
        "key": "completion_letter",
        "name": "Completion Letter",
        "roles": ["intern", "instructor", "facilitator", "teacher", "ambassador"],
        "body_text": (
            "{date}\n"
            "To Whom It May Concern,\n\n"
            "This is to confirm that {name} has successfully completed the {role} program at SpacePoint FZC, from {start_date} to {end_date}.\n\n"
            "{signature}\n"
            "{signatory_name}\n"
            "{signatory_title}"
        )
    },
    {
        "key": "certificate",
        "name": "Completion Certificate",
        "roles": ["intern", "instructor", "facilitator", "teacher", "ambassador"],
        "body_text": "in recognition of having successfully completed the<br/><b>SpacePoint {program}</b>"
    }
]


async def seed():
    async with AsyncSessionLocal() as session:
        print("Seeding document templates...")
        for t in DEFAULT_TEMPLATES:
            existing = (await session.execute(select(DocumentTemplate).where(DocumentTemplate.key == t["key"]))).scalars().first()
            if not existing:
                print(f"Adding template: {t['name']} ({t['key']})")
                session.add(
                    DocumentTemplate(
                        key=t["key"],
                        name=t["name"],
                        roles=t["roles"],
                        body_text=t["body_text"],
                    )
                )
            else:
                print(f"Template already exists: {t['key']}, skipping.")
        await session.commit()
        print("Seeding completed successfully!")


if __name__ == "__main__":
    asyncio.run(seed())
