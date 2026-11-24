"""End-to-end tests for LMS Interactive Books: admin authoring, .zip bundle extraction,
token-gated R2/local serving & runtime injection, access gates, progress & exercises,
analytics & CSV export, invite-code grants, Stripe fulfillment/refunds, and LMS programs.
"""

from __future__ import annotations

from datetime import date
import io
import json
import types
import uuid
import zipfile

import pytest
import stripe
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.models.instructors.invitation_code import InvitationCode
from app.models.lms.book import (
    LmsBook,
    LmsBookEnrollment,
    LmsBookProgress,
)
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.lms.purchase import Purchase
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.delivery_role import DeliveryRole
from app.models.sessions.session import Session, SessionInstructor
from app.models.user import User
from app.services.lms.checkout import fulfill
from app.services.lms.program import assign_lms_program

_MINI_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00"
    b"\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture(autouse=True)
def _isolated_book_storage(tmp_path, monkeypatch):
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(storage_dir))
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "local")
    monkeypatch.setattr(settings, "BOOKS_STORAGE_BACKEND", "local")


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id, user.role_values)}"}


async def _make_user(
    db: AsyncSession,
    role: str = "student",
    *,
    invite_code: str | None = None,
) -> User:
    user = User(
        id=uuid.uuid4(),
        full_name=f"{role.title()} {uuid.uuid4().hex[:6]}",
        email=f"{role}-{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        roles=[role],
        status="active",
        invitation_code_used=invite_code,
    )
    db.add(user)
    await db.flush()
    return user


def _build_book_zip(*, enclose_folder: bool = True, unsafe_member: str | None = None) -> bytes:
    buf = io.BytesIO()
    prefix = "satkit-mini/" if enclose_folder else ""
    manifest = {
        "schema_version": 1,
        "slug": "mini-satkit",
        "title": "Mini SatKit Book",
        "title_ar": "كتاب مصغر",
        "entry": "index.html",
        "languages": ["en", "ar"],
        "default_profile": "all",
        "profiles": [
            {
                "key": "all",
                "label_en": "Full Book",
                "label_ar": "الكتاب الكامل",
                "groups": [],
            },
            {
                "key": "uae10",
                "label_en": "UAE Grade 10",
                "label_ar": "الصف العاشر",
                "groups": ["u1"],
            },
        ],
        "outline": [
            {
                "key": "u1",
                "code": "U1",
                "part": "Physics Units",
                "title_en": "Orbits",
                "title_ar": "المدارات",
                "lessons": [
                    {
                        "spread": "sp-u1-1",
                        "title_en": "Gravity and Speed",
                        "title_ar": "الجاذبية والسرعة",
                        "game_keys": ["orbit"],
                    }
                ],
            },
            {
                "key": "m1",
                "code": "M1",
                "part": "SatKit Mission Labs",
                "title_en": "Telemetry Lab",
                "title_ar": "مختبر القياس",
                "lessons": [],
            },
        ],
    }
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if unsafe_member:
            zf.writestr(unsafe_member, "evil")
        zf.writestr(f"{prefix}book.json", json.dumps(manifest))
        zf.writestr(
            f"{prefix}index.html",
            "<!DOCTYPE html><html><head><title>Book</title></head><body><div class='brand'>SPACE.</div></body></html>",
        )
        zf.writestr(
            f"{prefix}sub/sim.html",
            "<!DOCTYPE html><html><head></head><body><h1>Sub Sim</h1></body></html>",
        )
    return buf.getvalue()


async def _upload_bundle(client: AsyncClient, ops: User, book_id: str, zip_bytes: bytes | None = None):
    payload = zip_bytes if zip_bytes is not None else _build_book_zip()
    return await client.post(
        f"/lms/admin/books/{book_id}/bundle",
        headers=_headers(ops),
        files={"file": ("book.zip", payload, "application/zip")},
    )


@pytest.mark.asyncio
async def test_admin_crud_publish_guard_and_role_permissions(db: AsyncSession, client: AsyncClient):
    student = await _make_user(db, "student")
    ops = await _make_user(db, "operations")
    await db.commit()

    # Non-staff cannot access admin book routes
    assert (await client.get("/lms/admin/books", headers=_headers(student))).status_code == 403
    assert (
        await client.post(
            "/lms/admin/books",
            headers=_headers(student),
            json={"title": "Blocked Book"},
        )
    ).status_code == 403

    # Ops creates a draft book
    res = await client.post(
        "/lms/admin/books",
        headers=_headers(ops),
        json={"title": "SpaceBook One", "access_mode": "open", "currency": "AED"},
    )
    assert res.status_code == 201, res.text
    created = res.json()
    assert created["is_published"] is False
    assert created["bundle_version"] == 0

    # Publishing without an uploaded bundle fails cleanly
    pub_fail = await client.post(
        f"/lms/admin/books/{created['id']}/publish",
        headers=_headers(ops),
    )
    assert pub_fail.status_code == 400


@pytest.mark.asyncio
async def test_bundle_upload_security_manifest_parsing_and_cover(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    await db.commit()

    create_res = await client.post(
        "/lms/admin/books",
        headers=_headers(ops),
        json={"title": "SatKit Book", "access_mode": "open"},
    )
    book_id = create_res.json()["id"]

    # Reject zip archive containing path traversal
    evil_zip = _build_book_zip(enclose_folder=False, unsafe_member="../escape.txt")
    bad_upload = await _upload_bundle(client, ops, book_id, evil_zip)
    assert bad_upload.status_code == 400

    # Valid zip unwraps top-level directory, bumps version, and extracts outline + profiles
    good_upload = await _upload_bundle(client, ops, book_id)
    assert good_upload.status_code == 200, good_upload.text
    meta = good_upload.json()
    assert meta["bundle_version"] == 1
    assert meta["chapters_detected"] == 2
    assert meta["profiles_detected"] == 2
    assert meta["files_uploaded"] == 3

    # Publish now succeeds
    pub_res = await client.post(f"/lms/admin/books/{book_id}/publish", headers=_headers(ops))
    assert pub_res.status_code == 200
    assert pub_res.json()["is_published"] is True

    # Cover rejects non-image and accepts PNG
    bad_cover = await client.post(
        f"/lms/admin/books/{book_id}/cover",
        headers=_headers(ops),
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert bad_cover.status_code == 400

    good_cover = await client.post(
        f"/lms/admin/books/{book_id}/cover",
        headers=_headers(ops),
        files={"file": ("cover.png", _MINI_PNG, "image/png")},
    )
    assert good_cover.status_code == 200, good_cover.text
    assert good_cover.json()["cover_url"] is not None


@pytest.mark.asyncio
async def test_token_gated_bundle_serving_and_runtime_injection(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    student = await _make_user(db, "student")
    await db.commit()

    book = (
        await client.post(
            "/lms/admin/books",
            headers=_headers(ops),
            json={"title": "Orbital Reader", "access_mode": "open"},
        )
    ).json()
    book_id = book["id"]
    await _upload_bundle(client, ops, book_id)
    await client.post(f"/lms/admin/books/{book_id}/publish", headers=_headers(ops))

    # Student session locks can_teacher to False; ops gets True
    stu_session = await client.post(
        f"/lms/books/{book_id}/reader-session",
        headers=_headers(student),
    )
    assert stu_session.status_code == 200, stu_session.text
    stu_data = stu_session.json()
    assert stu_data["can_teacher"] is False

    ops_session = await client.post(
        f"/lms/books/{book_id}/reader-session",
        headers=_headers(ops),
    )
    assert ops_session.status_code == 200
    assert ops_session.json()["can_teacher"] is True

    # Serving main entry injects config meta tag, bridge.js, and reader.css
    html_res = await client.get(stu_data["bundle_url"])
    assert html_res.status_code == 200
    assert 'name="sp-book-config"' in html_res.text
    assert "&quot;canTeacher&quot;: false" in html_res.text
    assert "__sp_runtime__/bridge.js" in html_res.text
    assert "__sp_runtime__/reader.css" in html_res.text

    # Serving sibling HTML sub-page and shared runtime assets with same token works
    token = stu_data["token"]
    sim_res = await client.get(f"/lms/books/read-bundle/{token}/sub/sim.html")
    assert sim_res.status_code == 200
    assert "Sub Sim" in sim_res.text

    bridge_res = await client.get(f"/lms/books/read-bundle/{token}/__sp_runtime__/bridge.js")
    assert bridge_res.status_code == 200
    css_res = await client.get(f"/lms/books/read-bundle/{token}/__sp_runtime__/reader.css")
    assert css_res.status_code == 200

    # Invalid token fails cleanly
    assert (await client.get("/lms/books/read-bundle/invalid-token/index.html")).status_code == 403


@pytest.mark.asyncio
async def test_cover_page_extraction_and_public_endpoint(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    await db.commit()

    book = (
        await client.post(
            "/lms/admin/books",
            headers=_headers(ops),
            json={"title": "Cover Test Book", "access_mode": "open"},
        )
    ).json()
    book_id = book["id"]

    # Draft book returns 404 on public cover-page
    assert book["cover_page_url"] is None
    assert (await client.get(f"/lms/books/public/{book_id}/cover-page")).status_code == 404

    html_doc = (
        "<!doctype html><html><head><style>.cover h1{color:#fff}</style></head><body>"
        '<div class="spread" data-name="cover">'
        '<article class="page cover"><div class="pin">'
        '<h1>First Page Title</h1>'
        '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="20"/></svg>'
        '<span class="brand">SPACE.</span>'
        '<button onclick="bad()">Open</button>'
        "<script>window.__EVIL__ = true;</script>"
        "</div></article></div>"
        '<div class="spread" data-name="ch1"><article class="page"><p>Later Chapter Body</p></article></div>'
        "</body></html>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("book.json", json.dumps({"entry": "index.html", "outline": [], "profiles": []}))
        zf.writestr("index.html", html_doc)

    up_res = await _upload_bundle(client, ops, book_id, buf.getvalue())
    assert up_res.status_code == 200
    assert (await client.get(f"/lms/books/public/{book_id}/cover-page")).status_code == 404

    pub_res = await client.post(f"/lms/admin/books/{book_id}/publish", headers=_headers(ops))
    assert pub_res.status_code == 200
    cover_page_url = pub_res.json()["cover_page_url"]
    assert cover_page_url == f"/lms/books/public/{book_id}/cover-page?v=1"

    pub_detail = (await client.get(f"/lms/books/public/{book_id}")).json()
    assert pub_detail["cover_page_url"] == cover_page_url

    cover_res = await client.get(cover_page_url)
    assert cover_res.status_code == 200
    assert "text/html" in cover_res.headers["content-type"]
    assert 'data-sp-cover-preview="1"' in cover_res.text
    assert "First Page Title" in cover_res.text
    assert "<circle" in cover_res.text
    assert "data:image/png;base64," in cover_res.text
    assert "<script" not in cover_res.text.lower()
    assert "__EVIL__" not in cover_res.text
    assert "onclick" not in cover_res.text.lower()
    assert "Later Chapter Body" not in cover_res.text


@pytest.mark.asyncio
async def test_invite_only_book_manual_grant_and_revoke(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    student = await _make_user(db, "student")
    await db.commit()

    book = (
        await client.post(
            "/lms/admin/books",
            headers=_headers(ops),
            json={"title": "Cohort Private Book", "access_mode": "invite"},
        )
    ).json()
    book_id = book["id"]
    await _upload_bundle(client, ops, book_id)
    await client.post(f"/lms/admin/books/{book_id}/publish", headers=_headers(ops))

    # Student blocked from self-enrolling or opening invite-only book
    assert (await client.post(f"/lms/books/{book_id}/enroll", headers=_headers(student))).status_code == 403
    assert (await client.post(f"/lms/books/{book_id}/reader-session", headers=_headers(student))).status_code == 403

    # Ops grants access by email
    grant_res = await client.post(
        f"/lms/admin/books/{book_id}/enrollments",
        headers=_headers(ops),
        json={"email": student.email},
    )
    assert grant_res.status_code == 201, grant_res.text
    assert grant_res.json()["status"] == "active"

    # Now student can read
    assert (await client.post(f"/lms/books/{book_id}/reader-session", headers=_headers(student))).status_code == 200

    # Revoke removes access
    revoke_res = await client.delete(
        f"/lms/admin/books/{book_id}/enrollments/{student.id}",
        headers=_headers(ops),
    )
    assert revoke_res.status_code == 204
    assert (await client.post(f"/lms/books/{book_id}/reader-session", headers=_headers(student))).status_code == 403


@pytest.mark.asyncio
async def test_progress_exercises_analytics_and_csv_export(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    student = await _make_user(db, "student")
    await db.commit()

    book = (
        await client.post(
            "/lms/admin/books",
            headers=_headers(ops),
            json={"title": "Analytics Book", "access_mode": "open"},
        )
    ).json()
    book_id = book["id"]
    await _upload_bundle(client, ops, book_id)
    await client.post(f"/lms/admin/books/{book_id}/publish", headers=_headers(ops))

    # Self-enroll and sync progress
    assert (await client.post(f"/lms/books/{book_id}/enroll", headers=_headers(student))).status_code == 200
    prog_res = await client.put(
        f"/lms/books/{book_id}/progress",
        headers=_headers(student),
        json={
            "current_spread": "sp-u1-1",
            "current_chapter": "u1",
            "active_profile": "uae10",
            "visited_spreads": ["sp-u1-1"],
            "stars": {"orbit": 2},
            "stars_earned": 2,
            "stars_possible": 10,
            "completion_pct": 45,
        },
    )
    assert prog_res.status_code == 200, prog_res.text
    assert prog_res.json()["completion_pct"] == 45

    # Submit quiz answer & notebook reflection
    quiz_res = await client.post(
        f"/lms/books/{book_id}/exercises",
        headers=_headers(student),
        json={
            "chapter_key": "u1",
            "exercise_key": "quiz:u1:q1",
            "exercise_type": "quiz",
            "prompt_text": "Why do satellites stay in orbit?",
            "answer_json": {"selected": "Horizontal velocity matches curvature"},
            "is_correct": True,
            "score_stars": 1,
            "max_stars": 1,
        },
    )
    assert quiz_res.status_code == 200

    nb_res = await client.post(
        f"/lms/books/{book_id}/exercises",
        headers=_headers(student),
        json={
            "chapter_key": "u1",
            "exercise_key": "nb:u1:1",
            "exercise_type": "notebook",
            "prompt_text": "Explain freefall.",
            "answer_json": {"text": "Falling around Earth continuously."},
        },
    )
    assert nb_res.status_code == 200

    # Analytics summary
    ana_res = await client.get(f"/lms/admin/books/{book_id}/analytics", headers=_headers(ops))
    assert ana_res.status_code == 200, ana_res.text
    ana = ana_res.json()
    assert ana["total_enrolled"] == 1
    assert ana["active_readers"] == 1
    assert ana["avg_completion_pct"] == 45
    assert ana["exercise_accuracy_pct"] == 100
    assert len(ana["learners"]) == 1
    assert ana["learners"][0]["notebook_count"] == 1
    assert any(ex["exercise_key"] == "quiz:u1:q1" for ex in ana["exercises"])
    assert ana["notebooks"][0]["answer_text"] == "Falling around Earth continuously."

    # CSV Export
    csv_res = await client.get(f"/lms/admin/books/{book_id}/analytics/export.csv", headers=_headers(ops))
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]
    assert student.email in csv_res.text
    assert "Falling around Earth continuously." in csv_res.text


@pytest.mark.asyncio
async def test_invite_code_grant_retroactive_enrollment(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    code = InvitationCode(
        id=uuid.uuid4(),
        code=f"BOOKS-{uuid.uuid4().hex[:6].upper()}",
        kind="student",
        is_active=True,
        max_uses=50,
        used_count=1,
    )
    db.add(code)
    holder = await _make_user(db, "student", invite_code=code.code)
    book = LmsBook(
        id=uuid.uuid4(),
        slug=f"grant-book-{uuid.uuid4().hex[:6]}",
        title="Invite Granted Book",
        access_mode="invite",
        is_published=True,
        bundle_version=1,
        created_by=ops.id,
    )
    db.add(book)
    await db.commit()

    resp = await client.post(
        f"/lms/admin/invite-codes/{code.id}/grants",
        headers=_headers(ops),
        json={"book_id": str(book.id)},
    )
    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert payload["accounts_enrolled"] == 1
    assert payload["grant"]["product_type"] == "book"
    assert payload["grant"]["book_title"] == book.title

    enr = (
        await db.execute(
            select(LmsBookEnrollment).where(
                LmsBookEnrollment.user_id == holder.id,
                LmsBookEnrollment.book_id == book.id,
            )
        )
    ).scalars().first()
    assert enr is not None
    assert enr.source == "invite_code"
    assert enr.status == "active"


@pytest.mark.asyncio
async def test_paid_book_checkout_fulfillment_and_refund_revocation(
    db: AsyncSession, client: AsyncClient, monkeypatch
):
    ops = await _make_user(db, "operations")
    student = await _make_user(db, "student")
    book = LmsBook(
        id=uuid.uuid4(),
        slug=f"paid-book-{uuid.uuid4().hex[:6]}",
        title="Paid Space Systems",
        access_mode="paid",
        price_cents=4900,
        currency="aed",
        is_published=True,
        bundle_version=1,
        created_by=ops.id,
    )
    db.add(book)
    await db.flush()
    purchase = Purchase(
        id=uuid.uuid4(),
        user_id=student.id,
        product_type="lms_book",
        book_id=book.id,
        amount_cents=4900,
        currency="aed",
        status="pending",
    )
    db.add(purchase)
    await db.commit()

    fake_session = types.SimpleNamespace(
        metadata={"purchase_id": str(purchase.id)},
        payment_status="paid",
        amount_total=4900,
        currency="aed",
        payment_intent="pi_book_refund_1",
    )
    result = await fulfill(db, fake_session)
    await db.commit()
    assert result.status == "paid"
    assert result.book_id == book.id

    enr = (
        await db.execute(
            select(LmsBookEnrollment).where(
                LmsBookEnrollment.user_id == student.id,
                LmsBookEnrollment.book_id == book.id,
            )
        )
    ).scalars().first()
    assert enr is not None
    assert enr.source == "purchase"
    assert enr.status == "active"

    # Refund revokes active book enrollment
    charge = types.SimpleNamespace(
        id="ch_book_1",
        refunded=True,
        payment_intent="pi_book_refund_1",
        amount_refunded=4900,
    )
    event = types.SimpleNamespace(
        type="charge.refunded",
        data=types.SimpleNamespace(object=charge),
    )
    monkeypatch.setattr(stripe.Webhook, "construct_event", lambda *a, **kw: event)
    wh_res = await client.post(
        "/lms/webhooks/stripe",
        content=b"{}",
        headers={"stripe-signature": "test-sig"},
    )
    assert wh_res.status_code == 200, wh_res.text

    await db.refresh(purchase)
    await db.refresh(enr)
    assert purchase.status == "refunded"
    assert enr.status == "inactive"


@pytest.mark.asyncio
async def test_lms_program_book_item_auto_enroll_and_completion(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    student = await _make_user(db, "student")
    program = Program(
        id=uuid.uuid4(),
        code=f"BK-{uuid.uuid4().hex[:6]}",
        name="Book Track Program",
        program_type="workshop",
        pricing_model="free",
        active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Book Cohort", status="running")
    db.add(cohort)
    await db.flush()
    lms_program = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Book Checklist")
    db.add(lms_program)
    await db.flush()

    book = LmsBook(
        id=uuid.uuid4(),
        slug=f"prog-book-{uuid.uuid4().hex[:6]}",
        title="Program Textbook",
        access_mode="invite",
        is_published=True,
        bundle_version=1,
        outline=[
            {
                "key": "u1",
                "code": "U1",
                "part": "Physics Units",
                "title_en": "Orbits",
                "lessons": [{"spread": "sp-u1-1", "title_en": "Gravity", "game_keys": []}],
            }
        ],
        created_by=ops.id,
    )
    db.add(book)
    await db.flush()

    item_pct = LmsProgramItem(
        id=uuid.uuid4(),
        owner_type="program",
        owner_id=lms_program.id,
        position=1,
        item_type="book",
        title="Read Half Book",
        book_id=book.id,
        book_profile="uae10",
        book_min_completion_pct=50,
    )
    item_ch = LmsProgramItem(
        id=uuid.uuid4(),
        owner_type="program",
        owner_id=lms_program.id,
        position=2,
        item_type="book",
        title="Read Unit 1",
        book_id=book.id,
        book_profile="uae10",
        book_chapter="u1",
    )
    db.add_all([item_pct, item_ch])
    await db.commit()

    assignment = await assign_lms_program(db, user_id=student.id, cohort_id=cohort.id)
    await db.commit()
    assert assignment is not None

    # Assigning auto-enrolls the student in the linked book
    enr = (
        await db.execute(
            select(LmsBookEnrollment).where(
                LmsBookEnrollment.user_id == student.id,
                LmsBookEnrollment.book_id == book.id,
            )
        )
    ).scalars().first()
    assert enr is not None
    assert enr.source == "program"
    assert enr.status == "active"

    # Initially pending
    checklist_1 = (await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))).json()
    pct_1 = next(i for i in checklist_1["items"] if i["id"] == str(item_pct.id))
    ch_1 = next(i for i in checklist_1["items"] if i["id"] == str(item_ch.id))
    assert pct_1["status"] == "pending"
    assert ch_1["status"] == "pending"
    assert ch_1["book_profile"] == "uae10"
    assert ch_1["book_chapter"] == "u1"

    # Below threshold (30 < 50) -> stays pending
    await client.put(
        f"/lms/books/{book.id}/progress",
        headers=_headers(student),
        json={"completion_pct": 30},
    )
    checklist_2 = (await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))).json()
    pct_2 = next(i for i in checklist_2["items"] if i["id"] == str(item_pct.id))
    assert pct_2["status"] == "pending"

    # Meets completion threshold (60 >= 50) + visits chapter spread -> both auto-complete
    await client.put(
        f"/lms/books/{book.id}/progress",
        headers=_headers(student),
        json={"completion_pct": 60, "visited_spreads": ["sp-u1-1"], "current_chapter": "u1"},
    )
    checklist_3 = (await client.get(f"/lms/programs/{assignment.id}", headers=_headers(student))).json()
    pct_3 = next(i for i in checklist_3["items"] if i["id"] == str(item_pct.id))
    ch_3 = next(i for i in checklist_3["items"] if i["id"] == str(item_ch.id))
    assert pct_3["status"] == "done"
    assert ch_3["status"] == "done"


@pytest.mark.asyncio
async def test_instructor_access_open_paid_grant_and_teaching_cohort(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    instructor = await _make_user(db, "instructor")

    open_book = LmsBook(
        id=uuid.uuid4(),
        slug=f"inst-open-{uuid.uuid4().hex[:6]}",
        title="Open Instructor Book",
        access_mode="open",
        is_published=True,
        bundle_version=1,
        created_by=ops.id,
    )
    paid_book = LmsBook(
        id=uuid.uuid4(),
        slug=f"inst-paid-{uuid.uuid4().hex[:6]}",
        title="Paid Instructor Book",
        access_mode="paid",
        price_cents=5000,
        currency="aed",
        is_published=True,
        bundle_version=1,
        created_by=ops.id,
    )
    invite_book = LmsBook(
        id=uuid.uuid4(),
        slug=f"inst-inv-{uuid.uuid4().hex[:6]}",
        title="Invite Instructor Book",
        access_mode="invite",
        is_published=True,
        bundle_version=1,
        created_by=ops.id,
    )
    cohort_book = LmsBook(
        id=uuid.uuid4(),
        slug=f"inst-coh-{uuid.uuid4().hex[:6]}",
        title="Cohort Teaching Book",
        access_mode="invite",
        is_published=True,
        bundle_version=1,
        created_by=ops.id,
    )
    db.add_all([open_book, paid_book, invite_book, cohort_book])
    await db.flush()

    # Attach cohort_book to an LMS program on a cohort this instructor teaches via SessionInstructor
    program = Program(
        id=uuid.uuid4(),
        code=f"IC-{uuid.uuid4().hex[:6]}",
        name="Instructor Cohort Program",
        program_type="workshop",
        pricing_model="free",
        active=True,
    )
    db.add(program)
    await db.flush()
    cohort = Cohort(id=uuid.uuid4(), program_id=program.id, name="Teaching Cohort", status="running")
    db.add(cohort)
    await db.flush()
    session = Session(id=uuid.uuid4(), cohort_id=cohort.id, meeting_date=date.today(), title="Session 1")
    db.add(session)
    await db.flush()
    role = DeliveryRole(
        id=uuid.uuid4(),
        name=f"Lead Instructor {uuid.uuid4().hex[:6]}",
    )
    db.add(role)
    await db.flush()
    db.add(SessionInstructor(id=uuid.uuid4(), session_id=session.id, user_id=instructor.id, role_id=role.id))
    lms_prog = LmsProgram(id=uuid.uuid4(), program_id=program.id, name="Teaching Checklist")
    db.add(lms_prog)
    await db.flush()
    db.add(
        LmsProgramItem(
            id=uuid.uuid4(),
            owner_type="program",
            owner_id=lms_prog.id,
            position=1,
            item_type="book",
            title="Cohort Book Item",
            book_id=cohort_book.id,
        )
    )
    await db.commit()

    # Catalog visibility: open, paid, and teaching-cohort books visible; ungranted invite book hidden
    cat = (await client.get("/lms/books", headers=_headers(instructor))).json()
    cat_ids = {b["id"] for b in cat}
    assert str(open_book.id) in cat_ids
    assert str(paid_book.id) in cat_ids
    assert str(cohort_book.id) in cat_ids
    assert str(invite_book.id) not in cat_ids

    # 1) Open book: allowed + can_teacher=True
    open_sess = await client.post(f"/lms/books/{open_book.id}/reader-session", headers=_headers(instructor))
    assert open_sess.status_code == 200
    assert open_sess.json()["can_teacher"] is True

    # 2) Paid book (ungranted): blocked (must pay)
    assert (await client.post(f"/lms/books/{paid_book.id}/reader-session", headers=_headers(instructor))).status_code == 403

    # 3) Teaching-cohort invite book: allowed + can_teacher=True
    coh_sess = await client.post(f"/lms/books/{cohort_book.id}/reader-session", headers=_headers(instructor))
    assert coh_sess.status_code == 200
    assert coh_sess.json()["can_teacher"] is True

    # 4) Other invite book: 404 detail & 403 reader until admin grants access
    assert (await client.get(f"/lms/books/{invite_book.id}", headers=_headers(instructor))).status_code == 404
    assert (await client.post(f"/lms/books/{invite_book.id}/reader-session", headers=_headers(instructor))).status_code == 403

    grant_res = await client.post(
        f"/lms/admin/books/{invite_book.id}/enrollments",
        headers=_headers(ops),
        json={"email": instructor.email},
    )
    assert grant_res.status_code == 201
    granted_sess = await client.post(f"/lms/books/{invite_book.id}/reader-session", headers=_headers(instructor))
    assert granted_sess.status_code == 200
    assert granted_sess.json()["can_teacher"] is True


@pytest.mark.asyncio
async def test_admin_user_search_include_students(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    tag = uuid.uuid4().hex[:6]
    student = await _make_user(db, "student")
    student.full_name = f"PickStudent {tag}"
    instructor = await _make_user(db, "instructor")
    instructor.full_name = f"PickStaff {tag}"
    await db.commit()

    staff_only = (
        await client.get("/lms/admin/users", params={"q": tag}, headers=_headers(ops))
    ).json()
    staff_ids = {u["id"] for u in staff_only}
    assert str(instructor.id) in staff_ids
    assert str(student.id) not in staff_ids

    with_students = (
        await client.get(
            "/lms/admin/users",
            params={"q": tag, "include_students": "true"},
            headers=_headers(ops),
        )
    ).json()
    all_ids = {u["id"] for u in with_students}
    assert str(instructor.id) in all_ids
    assert str(student.id) in all_ids


@pytest.mark.asyncio
async def test_book_bulk_grant_by_role(db: AsyncSession, client: AsyncClient):
    ops = await _make_user(db, "operations")
    student = await _make_user(db, "student")
    await db.commit()

    book = (
        await client.post(
            "/lms/admin/books",
            headers=_headers(ops),
            json={"title": "Bulk Grant Book", "access_mode": "invite"},
        )
    ).json()
    book_id = book["id"]

    res1 = await client.post(
        f"/lms/admin/books/{book_id}/enrollments/bulk",
        headers=_headers(ops),
        json={"role": "student"},
    )
    assert res1.status_code == 200, res1.text
    assert res1.json()["granted"] >= 1
    assert res1.json()["already_enrolled"] == 0

    res2 = await client.post(
        f"/lms/admin/books/{book_id}/enrollments/bulk",
        headers=_headers(ops),
        json={"role": "student"},
    )
    assert res2.status_code == 200
    assert res2.json()["granted"] == 0
    assert res2.json()["already_enrolled"] >= 1

    enr_rows = (
        await client.get(f"/lms/admin/books/{book_id}/enrollments", headers=_headers(ops))
    ).json()
    assert any(r["user_id"] == str(student.id) and r["status"] == "active" for r in enr_rows)
