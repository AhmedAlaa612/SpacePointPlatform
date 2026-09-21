"""Program Certificate Templates tests (2026-09).

Tests:
1. List, create, update, delete custom certificate templates for a program.
2. Setting custom template as program default (updates program.default_certificate_template_id).
3. Live PDF preview generation with custom coordinates, font sizes, and signature options.
4. Downloading cohort certificates with custom template layout.
"""

import io
import uuid
from unittest.mock import patch

from pypdf import PdfReader
import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.program_certificate_template import ProgramCertificateTemplate
from app.models.sessions.registration import Registration
from app.models.spine.contact import Contact
from app.models.user import User
from app.services.sessions.registration import register


def _headers(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _ops(db) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name="Cert Ops",
        email=f"certops-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=["operations"],
        status="active",
    )
    db.add(user)
    await db.flush()
    return user


async def _setup_program_and_cohort(db) -> tuple[Program, Cohort]:
    code = f"TMPL-{uuid.uuid4().hex[:8]}"
    program = Program(
        id=uuid.uuid4(),
        code=code,
        name="Custom Cert Championship",
        program_type="competition",
        pricing_model="free",
    )
    db.add(program)
    await db.flush()

    cohort = Cohort(
        id=uuid.uuid4(),
        program_id=program.id,
        name="2026 Nationals",
        status="running",
    )
    db.add(cohort)
    await db.flush()

    return program, cohort


@pytest.mark.asyncio
async def test_certificate_template_crud(db, client):
    ops = await _ops(db)
    program, cohort = await _setup_program_and_cohort(db)

    # 1. List initially empty
    res = await client.get(
        f"/sessions/programs/{program.id}/certificate-templates",
        headers=_headers(ops),
    )
    assert res.status_code == http_status.HTTP_200_OK
    assert res.json() == []

    # 2. Create template
    payload = {
        "name": "Gold Finalist Layout",
        "is_default": True,
        "background_type": "custom",
        "name_font_size": 38,
        "name_y": 310.0,
        "name_color": "#FFD700",
        "body_text": "For stellar achievement in<br/>{program_name}<br/>{dates}",
        "body_font_size": 22,
        "body_y": 250.0,
        "body_color": "#FFFFFF",
        "body_max_width": 650.0,
        "show_signature": True,
        "signature_y": 85.0,
        "signature_width": 150.0,
        "signature_height": 55.0,
    }
    create_res = await client.post(
        f"/sessions/programs/{program.id}/certificate-templates",
        json=payload,
        headers=_headers(ops),
    )
    assert create_res.status_code == http_status.HTTP_201_CREATED
    data = create_res.json()
    assert data["name"] == "Gold Finalist Layout"
    assert data["is_default"] is True
    assert data["name_font_size"] == 38
    template_id = data["id"]

    # Verify program default pointer updated
    await db.refresh(program)
    assert str(program.default_certificate_template_id) == template_id

    # 3. Update template
    update_res = await client.put(
        f"/sessions/programs/{program.id}/certificate-templates/{template_id}",
        json={"name_font_size": 42, "name_color": "#E5E5E5"},
        headers=_headers(ops),
    )
    assert update_res.status_code == http_status.HTTP_200_OK
    assert update_res.json()["name_font_size"] == 42
    assert update_res.json()["name_color"] == "#E5E5E5"

    # 4. Create second template and set as default
    create_res2 = await client.post(
        f"/sessions/programs/{program.id}/certificate-templates",
        json={"name": "Silver Layout", "is_default": False, "background_type": "light"},
        headers=_headers(ops),
    )
    template_id2 = create_res2.json()["id"]

    set_def_res = await client.post(
        f"/sessions/programs/{program.id}/certificate-templates/{template_id2}/set-default",
        headers=_headers(ops),
    )
    assert set_def_res.status_code == http_status.HTTP_200_OK
    assert set_def_res.json()["is_default"] is True

    # First template should no longer be default
    get1 = await client.get(
        f"/sessions/programs/{program.id}/certificate-templates/{template_id}",
        headers=_headers(ops),
    )
    assert get1.json()["is_default"] is False

    # 5. Delete template
    del_res = await client.delete(
        f"/sessions/programs/{program.id}/certificate-templates/{template_id}",
        headers=_headers(ops),
    )
    assert del_res.status_code == http_status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_certificate_template_preview(db, client):
    ops = await _ops(db)
    program, _cohort = await _setup_program_and_cohort(db)

    preview_payload = {
        "recipient_name": "سالم بن ناصر الوهيبي",
        "program_name": "Space Championship 2026",
        "cohort_name": "Senior Division",
        "dates": "October 2026",
        "location": "Sultan Qaboos University",
        "background_type": "dark",
        "name_font_size": 36,
        "name_y": 305.0,
        "name_color": "#9778be",
        "body_text": "For successfully completing<br/>{program_name}<br/>{dates}",
        "body_font_size": 20,
        "body_y": 255.0,
        "body_color": "#9778be",
        "body_max_width": 620.0,
        "show_signature": False,
    }

    res = await client.post(
        f"/sessions/programs/{program.id}/certificate-templates/preview",
        json=preview_payload,
        headers=_headers(ops),
    )
    assert res.status_code == http_status.HTTP_200_OK
    assert res.headers["content-type"] == "application/pdf"

    pdf_bytes = res.content
    assert len(pdf_bytes) > 50_000
    reader = PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1


@pytest.mark.asyncio
async def test_download_cohort_certificates_with_custom_template(db, client):
    ops = await _ops(db)
    program, cohort = await _setup_program_and_cohort(db)

    # Register student
    email = f"student-{uuid.uuid4().hex[:8]}@example.com"
    contact = Contact(
        id=uuid.uuid4(),
        full_name="Fatima Al-Kharusi",
        email=email,
        contact_roles=["student"],
        secondary_phones=[],
        preferred_language="en",
        lifecycle_stage="lead",
    )
    db.add(contact)
    await db.flush()
    reg = await register(
        db, contact_id=contact.id, cohort_id=cohort.id,
        registered_via="desk", payment_status="waived",
    )
    await db.flush()

    # Create custom template
    template = ProgramCertificateTemplate(
        id=uuid.uuid4(),
        program_id=program.id,
        name="Custom Finalist Template",
        is_default=True,
        background_type="dark",
        name_font_size=32,
        name_y=300.0,
        name_color="#B39DDB",
        body_text="Proudly awarded to<br/>{program_name}<br/>{dates}",
        body_font_size=18,
        body_y=250.0,
        body_color="#B39DDB",
    )
    db.add(template)
    await db.flush()
    program.default_certificate_template_id = template.id
    await db.flush()

    # Download with explicit template_id
    res = await client.get(
        f"/competitions/admin/cohorts/{cohort.id}/certificates/download?filter=all&template_id={template.id}",
        headers=_headers(ops),
    )
    assert res.status_code == http_status.HTTP_200_OK
    assert res.headers["content-type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(res.content))
    assert len(reader.pages) == 1


@pytest.mark.asyncio
async def test_stock_signatory_and_signature_preview(db, client):
    ops = await _ops(db)
    program, _cohort = await _setup_program_and_cohort(db)

    # 1. Test get_stock_signatory_info
    sig_info_res = await client.get("/sessions/programs/stock-signatory-info")
    assert sig_info_res.status_code == http_status.HTTP_200_OK
    sig_data = sig_info_res.json()
    assert "signatory_name" in sig_data
    assert "signatory_title" in sig_data
    assert sig_data["signatory_name"] == "ABDULLAH ALSALMANI"

    # 2. Test get_stock_signature_image fallback to static branding
    sig_img_res = await client.get("/sessions/programs/stock-signature-image?theme=dark")
    assert sig_img_res.status_code == http_status.HTTP_200_OK
    assert sig_img_res.headers["content-type"] == "image/png"
    assert len(sig_img_res.content) > 1000

    # 3. Test preview with show_signature = True and custom coordinates
    preview_res = await client.post(
        f"/sessions/programs/{program.id}/certificate-templates/preview",
        json={
            "recipient_name": "Nasser Al-Harthy",
            "program_name": "CanSat Competition",
            "background_type": "dark",
            "show_signature": True,
            "signature_x": 350.0,
            "signature_y": 80.0,
            "signature_width": 140.0,
        },
        headers=_headers(ops),
    )
    assert preview_res.status_code == http_status.HTTP_200_OK
    assert preview_res.headers["content-type"] == "application/pdf"
    reader = PdfReader(io.BytesIO(preview_res.content))
    assert len(reader.pages) == 1
