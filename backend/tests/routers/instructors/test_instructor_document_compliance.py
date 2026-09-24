import io
import uuid
import zipfile
from datetime import datetime, timezone
import pytest
import pytest_asyncio
import httpx

from app.core.security import create_access_token, get_password_hash
from app.db.session import get_db
from app.main import app
from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.instructors.instructor_document import InstructorDocument
from app.models.inventory.city import City
from app.models.user import User
from app.services import storage
from app.services.documents.compliance import evaluate_instructor_compliance


@pytest_asyncio.fixture
async def admin_user(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Compliance Admin",
        email=f"compliance-admin-{uuid.uuid4().hex[:8]}@example.com",
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
async def uae_instructor(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="UAE Instructor",
        email=f"uae-instructor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("password"),
        roles=["instructor"],
        status="active",
        country="AE",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def uae_headers(uae_instructor: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(uae_instructor.id, ['instructor'])}"}


@pytest_asyncio.fixture
async def intl_instructor(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Intl Instructor",
        email=f"intl-instructor-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("password"),
        roles=["instructor"],
        status="active",
        country="US",
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def intl_headers(intl_instructor: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(intl_instructor.id, ['instructor'])}"}


@pytest_asyncio.fixture
async def client(db):
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def test_compliance_uae_resident_all_required():
    user = User(id=uuid.uuid4(), full_name="Test UAE", country="AE")
    comp = evaluate_instructor_compliance(user, [])
    assert comp["is_uae_resident"] is True
    assert comp["is_complete"] is False
    assert comp["total_required"] == 5
    assert comp["uploaded_count"] == 0
    assert len(comp["missing_docs"]) == 5
    assert "Residence Visa" in comp["missing_docs"]


def test_compliance_intl_resident_visa_exempt():
    user = User(id=uuid.uuid4(), full_name="Test Intl", country="US")
    comp = evaluate_instructor_compliance(user, [])
    assert comp["is_uae_resident"] is False
    assert comp["is_complete"] is False
    assert comp["total_required"] == 4
    assert comp["uploaded_count"] == 0
    assert "Residence Visa" not in comp["missing_docs"]
    visa_item = next(it for it in comp["checklist"] if it["key"] == "visa")
    assert visa_item["exempt"] is True
    assert visa_item["mandatory"] is False


def test_compliance_intl_resident_complete_with_optional_visa():
    user = User(id=uuid.uuid4(), full_name="Test Intl", country="CA")
    docs = [
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="Passport", file_url="/f1"),
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="Emirates ID / National ID", file_url="/f2"),
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="Personal Picture", file_url="/f3"),
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="Clearance Document", file_url="/f4"),
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="Residence Visa", file_url="/f5"),
    ]
    comp = evaluate_instructor_compliance(user, docs)
    assert comp["is_uae_resident"] is False
    assert comp["is_complete"] is True
    assert comp["uploaded_count"] == 4
    assert comp["total_required"] == 4
    assert len(comp["missing_docs"]) == 0
    visa_item = next(it for it in comp["checklist"] if it["key"] == "visa")
    assert visa_item["exempt"] is True
    assert visa_item["uploaded"] is True


def test_compliance_legacy_aliases():
    user = User(id=uuid.uuid4(), full_name="Test Legacy", country="AE")
    docs = [
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="passport", file_url="/f1"),
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="ID Card", file_url="/f2"),
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="photo", file_url="/f3"),
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="Police Clearance", file_url="/f4"),
        InstructorDocument(id=uuid.uuid4(), user_id=user.id, document_type="Visa", file_url="/f5"),
    ]
    comp = evaluate_instructor_compliance(user, docs)
    assert comp["is_complete"] is True
    assert comp["uploaded_count"] == 5
    assert len(comp["missing_docs"]) == 0


@pytest.mark.asyncio
async def test_get_my_documents_compliance_api(client, db, uae_instructor, uae_headers):
    # Add one document
    doc = InstructorDocument(
        id=uuid.uuid4(),
        user_id=uae_instructor.id,
        document_type="Passport",
        file_url="/files/passport.pdf",
    )
    db.add(doc)
    await db.commit()

    resp = await client.get("/instructors/documents/compliance", headers=uae_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_uae_resident"] is True
    assert data["is_complete"] is False
    assert data["uploaded_count"] == 1
    assert data["total_required"] == 5
    assert len(data["checklist"]) == 5


@pytest.mark.asyncio
async def test_admin_instructors_compliance_and_detail(client, db, admin_user, admin_headers, uae_instructor):
    # Add a document for uae_instructor
    doc = InstructorDocument(
        id=uuid.uuid4(),
        user_id=uae_instructor.id,
        document_type="Clearance Document",
        file_url="/files/clearance.pdf",
    )
    db.add(doc)
    await db.commit()

    # List instructors
    list_resp = await client.get("/instructors/admin/instructors", headers=admin_headers)
    assert list_resp.status_code == 200
    instructors = list_resp.json()
    match = next((i for i in instructors if i["id"] == str(uae_instructor.id)), None)
    assert match is not None
    assert "docs_compliance" in match
    assert match["docs_compliance"]["is_complete"] is False
    assert match["docs_compliance"]["uploaded_count"] == 1
    assert match["docs_compliance"]["total_required"] == 5

    # Detail compliance
    detail_resp = await client.get(
        f"/instructors/admin/instructors/{uae_instructor.id}/documents-compliance",
        headers=admin_headers,
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["is_uae_resident"] is True
    assert detail["uploaded_count"] == 1
    clearance_item = next(it for it in detail["checklist"] if it["key"] == "clearance")
    assert clearance_item["uploaded"] is True


@pytest.mark.asyncio
async def test_admin_batch_documents_zip_success(client, db, admin_user, admin_headers, uae_instructor, intl_instructor):
    # Upload test document for uae_instructor
    file_path = f"{uae_instructor.id}_passport.pdf"
    content = b"%PDF-1.4 test uae passport"
    await storage.upload_to_path("instructor-documents", file_path, content, "application/pdf")

    doc = InstructorDocument(
        id=uuid.uuid4(),
        user_id=uae_instructor.id,
        document_type="Passport",
        bucket="instructor-documents",
        file_path=file_path,
        file_url=f"/files/instructor-documents/{file_path}",
    )
    db.add(doc)
    await db.commit()

    resp = await client.post(
        "/instructors/admin/instructors/documents/batch-zip",
        json={"user_ids": [str(uae_instructor.id), str(intl_instructor.id)]},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "instructors_documents_" in resp.headers["content-disposition"]

    # Verify folders in zip
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        namelist = zf.namelist()
        # Should have folder for UAE Instructor with passport
        assert any(name.startswith("UAE_Instructor/") and name.endswith("Passport.pdf") for name in namelist)
        # Should have folder for Intl Instructor with _no_documents_uploaded.txt marker
        assert any(name.startswith("Intl_Instructor/") and "_no_documents_uploaded.txt" in name for name in namelist)
