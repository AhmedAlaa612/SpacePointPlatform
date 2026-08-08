"""instructor_apply (POST /auth/instructor-apply) — structured city fields
(2026-08-08). No prior test coverage existed for this endpoint at all; this
covers just what this change touches: deliver_city_ids/city_of_residence_id
persist correctly onto the new ApplicantProfile columns.
"""

import json
import uuid

import pytest
from fastapi import status as http_status
from sqlalchemy import select

from app.models.instructors.applicant_profile import ApplicantProfile
from app.models.inventory.city import City
from app.models.user import User


@pytest.mark.asyncio
async def test_instructor_apply_persists_structured_city_fields(db, client):
    dubai = City(id=uuid.uuid4(), name=f"Dubai-{uuid.uuid4().hex[:6]}", country="AE")
    abu_dhabi = City(id=uuid.uuid4(), name=f"AbuDhabi-{uuid.uuid4().hex[:6]}", country="AE")
    db.add_all([dubai, abu_dhabi])
    await db.commit()

    payload = {
        "full_name": "Apply Cities Test",
        "email": f"apply-cities-{uuid.uuid4().hex[:8]}@example.com",
        "password": "s3cret-pass",
        "city_of_residence_id": str(dubai.id),
        "deliver_city_ids": [str(dubai.id), str(abu_dhabi.id)],
        "background_areas": ["Engineering"],
        "has_own_transportation": True,
        "country": "United Arab Emirates",
    }
    # Mixing Form()+File() on the endpoint forces multipart parsing even
    # when no file is attached — the `files=` dict (rather than `data=`
    # alone) is what makes httpx encode the request as multipart/form-data.
    resp = await client.post(
        "/auth/instructor-apply",
        data={"payload": json.dumps(payload)},
        files={"cv": ("", b"", "application/octet-stream")},
    )
    assert resp.status_code == http_status.HTTP_201_CREATED, resp.text

    user = (await db.execute(select(User).where(User.email == payload["email"]))).scalars().first()
    assert user is not None
    profile = (await db.execute(
        select(ApplicantProfile).where(ApplicantProfile.user_id == user.id)
    )).scalars().first()
    assert profile is not None
    assert profile.city_of_residence_id == dubai.id
    assert set(profile.deliver_city_ids) == {dubai.id, abu_dhabi.id}
