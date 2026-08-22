"""scripts/rerender_signed_contracts.py — the --email scope added 2026-08-22
so one reported-broken contract can be fixed without touching everyone
else's already-signed PDF. Stubs `generate_contract_pdf`/`storage.upload_file`
so this never shells out to the real LibreOffice conversion — the point here
is the query scoping, not PDF rendering."""

import uuid
from datetime import datetime, timezone

import pytest

from app.models.instructors.instructor_profile import InstructorProfile
from app.models.user import User
import scripts.rerender_signed_contracts as script
from scripts.rerender_signed_contracts import rerender_signed_contracts


def _signed_instructor(**overrides) -> tuple[User, InstructorProfile]:
    user_id = uuid.uuid4()
    defaults = dict(
        id=user_id, full_name="Test Instructor", email=f"{uuid.uuid4().hex}@example.com",
        password_hash="x", roles=["instructor"],
    )
    defaults.update({k: v for k, v in overrides.items() if k in defaults})
    user = User(**defaults)
    profile = InstructorProfile(
        user_id=user_id,
        signed_contract_path=overrides.get("signed_contract_path", f"{user_id}/signed.pdf"),
        contract_signature_data=overrides.get("contract_signature_data", "data:image/png;base64,AAA="),
        contract_signed_at=overrides.get("contract_signed_at", datetime.now(timezone.utc)),
    )
    return user, profile


@pytest.fixture(autouse=True)
def _stub_rendering(monkeypatch):
    monkeypatch.setattr(script, "generate_contract_pdf", lambda *a, **kw: b"%PDF-fake")

    async def _fake_upload(bucket, path, data, content_type):
        return f"https://storage.test/{bucket}/{path}"

    monkeypatch.setattr(script.storage, "upload_file", _fake_upload)


@pytest.mark.asyncio
async def test_email_scopes_to_only_that_one_instructor(db):
    user_a, profile_a = _signed_instructor()
    user_b, profile_b = _signed_instructor()
    db.add_all([user_a, user_b])
    await db.flush()
    db.add_all([profile_a, profile_b])
    await db.flush()

    rerendered, skipped = await rerender_signed_contracts(db, email=user_a.email)

    assert rerendered == 1
    assert skipped == 0
    assert profile_a.signed_contract_url == f"https://storage.test/contracts/{profile_a.signed_contract_path}"
    assert profile_b.signed_contract_url is None


@pytest.mark.asyncio
async def test_no_email_processes_every_signed_contract(db):
    user_a, profile_a = _signed_instructor()
    user_b, profile_b = _signed_instructor()
    db.add_all([user_a, user_b])
    await db.flush()
    db.add_all([profile_a, profile_b])
    await db.flush()

    rerendered, skipped = await rerender_signed_contracts(db)

    assert rerendered == 2
    assert skipped == 0


@pytest.mark.asyncio
async def test_email_with_no_matching_signed_contract_touches_nothing(db):
    user_a, profile_a = _signed_instructor()
    db.add(user_a)
    await db.flush()
    db.add(profile_a)
    await db.flush()

    rerendered, skipped = await rerender_signed_contracts(db, email="nobody@example.com")

    assert (rerendered, skipped) == (0, 0)
    assert profile_a.signed_contract_url is None


@pytest.mark.asyncio
async def test_dry_run_with_email_writes_nothing(db):
    user_a, profile_a = _signed_instructor()
    db.add(user_a)
    await db.flush()
    db.add(profile_a)
    await db.flush()

    rerendered, skipped = await rerender_signed_contracts(db, dry_run=True, email=user_a.email)

    assert rerendered == 1
    assert profile_a.signed_contract_url is None
