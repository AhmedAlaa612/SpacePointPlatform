import io
import uuid
import zipfile

import httpx
import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.instructors.instructor_document import InstructorDocument
from app.models.user import User
from app.services import storage


@pytest_asyncio.fixture
async def admin_user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Admin User",
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("password"),
        roles=["admin"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def admin_headers(admin_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(admin_user.id, ['admin'])}"}


@pytest_asyncio.fixture
async def regular_user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Instructor User",
        email=f"instructor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("password"),
        roles=["instructor"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_download_user_documents_zip_returns_404_when_no_docs(client, admin_headers, regular_user):
    resp = await client.get(f"/admin/users/{regular_user.id}/documents/zip", headers=admin_headers)
    assert resp.status_code == 404
    assert "No uploaded documents found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_download_user_documents_zip_success(db, client, admin_headers, regular_user):
    # Upload test document to storage
    file_path = f"{regular_user.id}_passport.pdf"
    content = b"%PDF-1.4 test passport content"
    await storage.upload_to_path("instructor-documents", file_path, content, "application/pdf")

    # Add database record
    doc = InstructorDocument(
        id=uuid.uuid4(),
        user_id=regular_user.id,
        document_type="Passport",
        bucket="instructor-documents",
        file_path=file_path,
        file_url=f"/files/instructor-documents/{file_path}",
    )
    db.add(doc)
    await db.commit()

    resp = await client.get(f"/admin/users/{regular_user.id}/documents/zip", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "Instructor_User_documents.zip" in resp.headers["content-disposition"]

    # Verify zip content
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        namelist = zf.namelist()
        assert len(namelist) == 1
        assert namelist[0] == "Passport.pdf"
        assert zf.read(namelist[0]) == content


@pytest.mark.asyncio
async def test_instructor_admin_alias_route(db, client, admin_headers, regular_user):
    resp = await client.get(f"/instructors/admin/instructors/{regular_user.id}/documents/zip", headers=admin_headers)
    # Since no docs, returns 404
    assert resp.status_code == 404
