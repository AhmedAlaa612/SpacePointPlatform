"""Integration tests for configurable application form fields, custom questions,
answer snapshotting, and enriched admin review + cross-platform footprint.
"""

import json
import uuid

import pytest
from sqlalchemy import select

from app.core.security import create_access_token, get_password_hash
from app.models.application import Application
from app.models.inventory.city import City
from app.models.spine.contact import Contact
from app.models.user import User


def _admin_headers(admin: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(admin.id, ['admin'])}"}


async def _make_admin(db) -> User:
    admin = User(
        id=uuid.uuid4(),
        full_name="Test Admin",
        email=f"admin-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("not-a-real-password"),
        roles=["admin"],
        status="active",
    )
    db.add(admin)
    await db.flush()
    return admin


@pytest.mark.asyncio
async def test_form_config_overrides_enforce_required_and_optional_fields(db, client):
    admin = await _make_admin(db)
    headers = _admin_headers(admin)

    city = City(id=uuid.uuid4(), name=f"Sharjah-{uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.flush()

    initial = await client.get("/admin/applications/form-config/intern", headers=headers)
    assert initial.status_code == 200, initial.text
    fields = initial.json()["fields"]

    updated_fields = []
    for item in fields:
        if item["key"] == "phone":
            updated_fields.append({"key": "phone", "enabled": True, "required": True})
        elif item["key"] == "cv":
            updated_fields.append({"key": "cv", "enabled": True, "required": False})
        else:
            updated_fields.append({"key": item["key"], "enabled": item["enabled"], "required": item["required"]})

    saved = await client.put(
        "/admin/applications/form-config/intern",
        json={"fields": updated_fields},
        headers=headers,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["has_custom_override"] is True

    public_cfg = await client.get("/apply/intern/form-config")
    assert public_cfg.status_code == 200, public_cfg.text
    by_key = {f["key"]: f for f in public_cfg.json()["fields"]}
    assert by_key["phone"]["required"] is True
    assert by_key["cv"]["required"] is False

    # Missing newly required phone -> 400
    missing_phone = await client.post(
        "/apply/intern",
        data={
            "full_name": "Nadia Karim",
            "email": f"nadia-{uuid.uuid4().hex[:8]}@example.com",
            "password": "secret-password",
            "country": "AE",
            "city_id": str(city.id),
        },
    )
    assert missing_phone.status_code == 400, missing_phone.text
    assert "Phone" in missing_phone.text

    # Providing phone without CV succeeds when CV was toggled optional
    valid = await client.post(
        "/apply/intern",
        data={
            "full_name": "Nadia Karim",
            "email": f"nadia-{uuid.uuid4().hex[:8]}@example.com",
            "password": "secret-password",
            "phone": "+971501112233",
            "nationality": "United Arab Emirates",
            "country": "AE",
            "city_id": str(city.id),
            "university": "UAE University",
            "major": "Aerospace Engineering",
            "preferred_city_id": str(city.id),
            "requested_duration_weeks": "8",
        },
    )
    assert valid.status_code == 201, valid.text
    app_id = valid.json()["id"]

    # Detail at pending status still exposes intern_details
    detail = await client.get(f"/admin/applications/{app_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["intern_details"] is not None
    assert body["intern_details"]["university"] == "UAE University"
    assert body["intern_details"]["major"] == "Aerospace Engineering"
    assert body["intern_details"]["preferred_city_name"] == city.name
    assert body["intern_details"]["requested_duration_weeks"] == 8


@pytest.mark.asyncio
async def test_custom_question_crud_reorder_validation_and_deleted_snapshot_resolution(db, client):
    admin = await _make_admin(db)
    headers = _admin_headers(admin)

    city = City(id=uuid.uuid4(), name=f"Dubai-{uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.flush()

    q1 = await client.post(
        "/admin/applications/questions",
        json={
            "audience": "ambassador",
            "question_text": "Portfolio URL",
            "question_type": "url",
            "required": True,
            "options": [],
        },
        headers=headers,
    )
    assert q1.status_code == 200, q1.text
    q1_id = q1.json()["id"]

    q2 = await client.post(
        "/admin/applications/questions",
        json={
            "audience": "ambassador",
            "question_text": "Preferred outreach tracks",
            "question_type": "multiple_choice",
            "required": False,
            "options": ["Schools", "Universities", "Community"],
        },
        headers=headers,
    )
    assert q2.status_code == 200, q2.text
    q2_id = q2.json()["id"]

    reordered = await client.post(
        "/admin/applications/questions/reorder",
        json={"audience": "ambassador", "ordered_ids": [q2_id, q1_id]},
        headers=headers,
    )
    assert reordered.status_code == 200, reordered.text
    assert [q["id"] for q in reordered.json()] == [q2_id, q1_id]

    public_qs = await client.get("/apply/ambassador/questions")
    assert public_qs.status_code == 200
    assert [q["id"] for q in public_qs.json()] == [q2_id, q1_id]

    # Missing required custom question -> 400
    missing_q = await client.post(
        "/apply/ambassador",
        data={
            "full_name": "Tariq Mansoor",
            "email": f"tariq-{uuid.uuid4().hex[:8]}@example.com",
            "password": "secret-password",
            "country": "AE",
            "city_id": str(city.id),
            "answers": json.dumps({q2_id: ["Schools", "Universities"]}),
        },
    )
    assert missing_q.status_code == 400, missing_q.text

    # Spine contact + earlier application prior to new submission
    applicant_email = f"tariq-full-{uuid.uuid4().hex[:8]}@example.com"
    contact = Contact(
        id=uuid.uuid4(),
        full_name="Tariq Prior",
        email=applicant_email,
        primary_phone_e164="+971509998877",
        country="AE",
        city="Dubai",
    )
    prior_app = Application(
        id=uuid.uuid4(),
        role="teacher",
        status="rejected",
        full_name="Tariq Prior",
        email=applicant_email,
        password_hash=get_password_hash("secret-password"),
        answers={},
    )
    db.add_all([contact, prior_app])
    await db.flush()

    submitted = await client.post(
        "/apply/ambassador",
        data={
            "full_name": "Tariq Mansoor",
            "email": applicant_email,
            "password": "secret-password",
            "country": "AE",
            "city_id": str(city.id),
            "answers": json.dumps({
                q1_id: "https://example.com/portfolio",
                q2_id: ["Schools", "Community"],
            }),
        },
    )
    assert submitted.status_code == 201, submitted.text
    app_id = submitted.json()["id"]

    # Also verify existing User matching by email appears in footprint (e.g. onboarded from another track)
    existing_user = User(
        id=uuid.uuid4(),
        full_name="Tariq Prior",
        email=applicant_email,
        password_hash=get_password_hash("secret-password"),
        roles=["student"],
        status="active",
        phone="+971509998877",
    )
    db.add(existing_user)
    await db.flush()

    # Soft-delete q1 before admin reviews the application
    deleted = await client.delete(f"/admin/applications/questions/{q1_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    detail = await client.get(f"/admin/applications/{app_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    data = detail.json()

    resolved_by_key = {item["key"]: item for item in data["resolved_answers"]}
    assert resolved_by_key[q1_id]["label"] == "Portfolio URL"
    assert resolved_by_key[q1_id]["value"] == "https://example.com/portfolio"
    assert resolved_by_key[q1_id]["is_deleted"] is True
    assert resolved_by_key[q2_id]["label"] == "Preferred outreach tracks"
    assert resolved_by_key[q2_id]["value"] == ["Schools", "Community"]
    assert resolved_by_key[q2_id]["is_deleted"] is False

    fp = data["platform_footprint"]
    assert fp is not None
    assert fp["existing_user"]["id"] == str(existing_user.id)
    assert fp["spine_contact"]["id"] == str(contact.id)
    assert any(a["id"] == str(prior_app.id) for a in fp["other_applications"])


@pytest.mark.asyncio
async def test_instructor_apply_custom_questions_and_enriched_applicant_review(db, client):
    admin = await _make_admin(db)
    headers = _admin_headers(admin)

    city = City(id=uuid.uuid4(), name=f"AbuDhabi-{uuid.uuid4().hex[:6]}", country="AE")
    db.add(city)
    await db.flush()

    q_resp = await client.post(
        "/admin/applications/questions",
        json={
            "audience": "instructor",
            "question_text": "Years of STEM workshop experience",
            "question_type": "number",
            "required": True,
            "options": [],
        },
        headers=headers,
    )
    assert q_resp.status_code == 200, q_resp.text
    q_id = q_resp.json()["id"]

    email = f"inst-{uuid.uuid4().hex[:8]}@example.com"
    base_payload = {
        "full_name": "Laila Almansoori",
        "email": email,
        "password": "strong-password",
        "phone": "+971504445566",
        "country": "AE",
        "city_of_residence_id": str(city.id),
        "deliver_city_ids": [str(city.id)],
        "background_areas": ["Robotics"],
        "has_own_transportation": True,
    }

    # Missing required instructor question -> 400
    missing_ans = await client.post(
        "/auth/instructor-apply",
        data={"payload": json.dumps(base_payload)},
        files={"cv": ("", b"", "application/octet-stream")},
    )
    assert missing_ans.status_code == 400, missing_ans.text

    # Valid submission persists phone, city_id, and instructor answers
    full_payload = {**base_payload, "answers": {q_id: "5"}}
    ok = await client.post(
        "/auth/instructor-apply",
        data={"payload": json.dumps(full_payload)},
        files={"cv": ("", b"", "application/octet-stream")},
    )
    assert ok.status_code == 201, ok.text

    user = (await db.execute(select(User).where(User.email == email))).scalars().first()
    assert user is not None
    assert user.phone == "+971504445566"
    assert user.city_id == city.id

    review_resp = await client.get(f"/instructors/admin/applicants/{user.id}", headers=headers)
    assert review_resp.status_code == 200, review_resp.text
    detail = review_resp.json()
    assert detail["phone"] == "+971504445566"
    assert detail["country"] == "AE"
    assert detail["profile"]["deliver_cities"] == [city.name]
    assert detail["review"] is not None
    assert any(a["key"] == q_id and a["label"] == "Years of STEM workshop experience" and a["value"] == "5" for a in detail["custom_answers"])
    assert detail["platform_footprint"] is not None


@pytest.mark.asyncio
async def test_question_visibility_toggle_and_student_signup_config(db, client):
    admin = await _make_admin(db)
    headers = _admin_headers(admin)

    # Nationality is mandatory by default for intern, instructor, and student
    for role in ("intern", "instructor", "student"):
        cfg_resp = await client.get(f"/apply/{role}/form-config")
        assert cfg_resp.status_code == 200, cfg_resp.text
        nat_field = next((f for f in cfg_resp.json()["fields"] if f["key"] == "nationality"), None)
        assert nat_field is not None and nat_field["enabled"] is True and nat_field["required"] is True

    # Create required custom question for student and verify visibility toggle
    q_resp = await client.post(
        "/admin/applications/questions",
        json={
            "audience": "student",
            "question_text": "Grade / Academic Level",
            "question_type": "text",
            "required": True,
            "options": [],
        },
        headers=headers,
    )
    assert q_resp.status_code == 200, q_resp.text
    q_id = q_resp.json()["id"]

    # Hide question -> excluded from public /apply/student/questions and not enforced on signup
    hide_resp = await client.patch(
        f"/admin/applications/questions/{q_id}",
        json={"enabled": False},
        headers=headers,
    )
    assert hide_resp.status_code == 200, hide_resp.text
    assert hide_resp.json()["enabled"] is False

    public_qs = await client.get("/apply/student/questions")
    assert public_qs.status_code == 200
    assert all(q["id"] != q_id for q in public_qs.json())

    student_email_1 = f"stud1-{uuid.uuid4().hex[:8]}@example.com"
    ok_hidden = await client.post(
        "/auth/signup",
        json={
            "full_name": "Noor Ali",
            "email": student_email_1,
            "password": "strong-password",
            "phone": "+971501112233",
            "nationality": "United Arab Emirates",
        },
    )
    assert ok_hidden.status_code == 201, ok_hidden.text

    # Re-enable question -> enforced on student signup
    show_resp = await client.patch(
        f"/admin/applications/questions/{q_id}",
        json={"enabled": True},
        headers=headers,
    )
    assert show_resp.status_code == 200, show_resp.text
    assert show_resp.json()["enabled"] is True

    student_email_2 = f"stud2-{uuid.uuid4().hex[:8]}@example.com"
    missing_q = await client.post(
        "/auth/signup",
        json={
            "full_name": "Omar Hassan",
            "email": student_email_2,
            "password": "strong-password",
            "phone": "+971501112244",
            "nationality": "Egypt",
        },
    )
    assert missing_q.status_code == 400, missing_q.text

    ok_answered = await client.post(
        "/auth/signup",
        json={
            "full_name": "Omar Hassan",
            "email": student_email_2,
            "password": "strong-password",
            "phone": "+971501112244",
            "nationality": "Egypt",
            "answers": {q_id: "Grade 11"},
        },
    )
    assert ok_answered.status_code == 201, ok_answered.text


@pytest.mark.asyncio
async def test_all_public_apply_roles_and_organization_submit_cleanly(db, client):
    city = City(id=uuid.uuid4(), name=f"Dubai-{uuid.uuid4().hex[:6]}", country="AE")
    amb = User(
        id=uuid.uuid4(),
        full_name="Amb Ref",
        email=f"ambref-{uuid.uuid4().hex[:8]}@example.com",
        password_hash=get_password_hash("secret-password"),
        roles=["ambassador"],
        status="active",
        invite_code=f"AMB{uuid.uuid4().hex[:5].upper()}",
    )
    db.add_all([city, amb])
    await db.flush()

    for role in ("ambassador", "facilitator"):
        r = await client.post(
            f"/apply/{role}",
            data={
                "full_name": f"Test {role}",
                "email": f"{role}-{uuid.uuid4().hex[:8]}@example.com",
                "password": "strong-password",
                "country": "AE",
                "city_id": str(city.id),
            },
        )
        assert r.status_code == 201, f"{role} failed: {r.text}"

    teacher_r = await client.post(
        "/apply/teacher",
        data={
            "full_name": "Test Teacher",
            "email": f"teacher-{uuid.uuid4().hex[:8]}@example.com",
            "password": "strong-password",
            "country": "AE",
            "city_id": str(city.id),
            "invite_code": amb.invite_code,
        },
    )
    assert teacher_r.status_code == 201, f"teacher failed: {teacher_r.text}"

    org_r = await client.post(
        "/auth/organization-signup",
        json={
            "org_name_latin": f"Space Club {uuid.uuid4().hex[:6]}",
            "org_type": "university",
            "country": "AE",
            "city": "Dubai",
            "full_name": "Org Contact",
            "email": f"org-{uuid.uuid4().hex[:8]}@example.com",
            "phone": "+971501234567",
            "password": "strong-password",
        },
    )
    assert org_r.status_code == 201, f"organization-signup failed: {org_r.text}"
