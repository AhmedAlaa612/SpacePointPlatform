import asyncio
from sqlalchemy import text
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE videos SET storage_backend = NULL WHERE id = :id"),
            {"id": "24da3df9-27e6-460c-b5c9-c71485985348"},
        )
        await db.commit()
        row = (await db.execute(
            text("SELECT id, status, storage_backend FROM videos WHERE id = :id"),
            {"id": "24da3df9-27e6-460c-b5c9-c71485985348"},
        )).first()
        print("after update:", row)

asyncio.run(main())
