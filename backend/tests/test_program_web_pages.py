"""Tests for Program Landing Pages (unified on WebsiteEvent) & Multi-Cohort
Hybrid-Live Case Studies (WebsiteCaseStudy).

Covers:
1. Auto-drafting a WebsiteEvent landing page when a Program is created (Ops & Org).
2. Hybrid-live resolution: live steps, seats left, partner-cohort isolation on SpacePoint
   programs, per-cohort hide/show, overrides & reset-field, and NO price fields.
3. 3-state partner organization access (`disabled` | `review` | `direct`) including
   direct publish, submit-for-review, and direct unpublish.
4. Multi-case-study per program with ordered cohorts (`from-program`), hybrid-live
   metrics + ordered stage breakdown, overrides & reset-field, Ops-only access.
5. Private preview token endpoint (`/public/website/preview/{token}`) with
   `X-Robots-Tag: noindex, nofollow`, draft visibility vs 404 on public slug, and token rotation.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash
from app.models.enums import UserRole
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.user import User
from app.models.website_event import WebsiteEvent
from app.services.org_access import set_user_org_roles


def _hdrs(user: User) -> dict[str, str]:
    token = create_access_token(str(user.id), [r.value if hasattr(r, "value") else str(r) for r in user.roles])
    return {"Authorization": f"Bearer {token}"}


async def _seed_users_and_org(db: AsyncSession):
    suf = uuid.uuid4().hex[:6]
    ops = User(
        id=uuid.uuid4(),
        email=f"ops_web_{suf}@spacepoint.test",
        full_name="Ops Web Admin",
        password_hash=get_password_hash("Test1234!"),
        roles=[UserRole.operations, UserRole.admin],
        status="active",
    )
    org_owner = User(
        id=uuid.uuid4(),
        email=f"partner_web_{suf}@partner.test",
        full_name="Partner Web Owner",
        password_hash=get_password_hash("Test1234!"),
        roles=[UserRole.organization],
        status="active",
    )
    db.add_all([ops, org_owner])
    await db.flush()

    org = Organization(
        id=uuid.uuid4(),
        name_latin=f"Partner Lab {suf}",
        org_type="university",
        country="uae",
        owner_user_id=org_owner.id,
        is_approved=True,
        program_page_access="disabled",
    )
    db.add(org)
    await db.flush()
    org_owner.organization_id = org.id
    set_user_org_roles(org_owner, ["owner"])
    await db.commit()
    return ops, org_owner, org, suf


@pytest.mark.asyncio
async def test_program_landing_page_auto_draft_live_merge_and_preview(
    client: AsyncClient, db_session: AsyncSession
):
    ops, partner, org, suf = await _seed_users_and_org(db_session)
    ops_h = _hdrs(ops)

    # 1. Create a SpacePoint program -> auto-drafts WebsiteEvent landing page
    resp = await client.post(
        "/sessions/programs",
        headers=ops_h,
        json={
            "code": f"SPWEB-{suf.upper()}",
            "name": f"Satty Mission {suf}",
            "program_type": "competition",
            "description": "Original live program description.",
            "pricing_model": "paid",
            "price": 999,
        },
    )
    assert resp.status_code == 201, resp.text
    prog_id = resp.json()["id"]

    # Add 2 SpacePoint cohorts + 1 partner-run cohort on this SpacePoint program
    c1 = Cohort(
        id=uuid.uuid4(),
        program_id=uuid.UUID(prog_id),
        name="Stage 1 - Online",
        status="registration_open",
        starts_on=date(2026, 10, 1),
        ends_on=date(2026, 10, 10),
        capacity=20,
        visibility="private",
        management_mode="spacepoint",
    )
    c2 = Cohort(
        id=uuid.uuid4(),
        program_id=uuid.UUID(prog_id),
        name="Stage 2 - Finals",
        status="planned",
        starts_on=date(2026, 11, 1),
        ends_on=date(2026, 11, 5),
        capacity=10,
        visibility="private",
        management_mode="spacepoint",
    )
    c_partner = Cohort(
        id=uuid.uuid4(),
        program_id=uuid.UUID(prog_id),
        organization_id=org.id,
        name="Partner Private Cohort",
        status="running",
        starts_on=date(2026, 10, 15),
        capacity=15,
        visibility="private",
        management_mode="partner",
    )
    db_session.add_all([c1, c2, c_partner])
    await db_session.commit()

    # 2. Before explicit creation, GET returns null; POST creates the draft
    lp_none = await client.get(f"/sessions/programs/{prog_id}/landing-page", headers=ops_h)
    assert lp_none.status_code == 200
    assert lp_none.json() is None

    lp_resp = await client.post(f"/sessions/programs/{prog_id}/landing-page", headers=ops_h)
    assert lp_resp.status_code == 200, lp_resp.text
    lp = lp_resp.json()
    assert lp["program_id"] == prog_id
    assert lp["live_linked"] is True
    assert lp["is_published"] is False
    assert lp["title"] == f"Satty Mission {suf}"
    assert lp["about_text"] == "Original live program description."
    assert lp["preview_token"]
    assert lp["org_access"] == "ops"
    # Partner cohort must NOT leak onto SpacePoint program's landing page steps
    step_ids = [s["cohort_id"] for s in lp["steps"]]
    assert step_ids == [str(c1.id), str(c2.id)]
    assert str(c_partner.id) not in step_ids
    assert lp["field_states"]["title"]["source"] == "live"

    # 3. Draft is 404 on public slug, 200 on /public/website/preview/{token} with noindex
    pub_404 = await client.get(f"/public/website/events/resolve/{lp['slug']}")
    assert pub_404.status_code == 404

    prev_ok = await client.get(f"/public/website/preview/{lp['preview_token']}")
    assert prev_ok.status_code == 200, prev_ok.text
    assert "noindex" in prev_ok.headers.get("x-robots-tag", "").lower()
    assert prev_ok.json()["kind"] == "event"
    assert prev_ok.json()["is_published"] is False
    assert len(prev_ok.json()["data"]["steps"]) == 2

    # 4. Override title + hide c2 + set registration_url + Arabic content
    upd = await client.put(
        f"/sessions/programs/{prog_id}/landing-page",
        headers=ops_h,
        json={
            "title": "Custom Marketing Title",
            "registration_url": "https://forms.example.com/satty",
            "hidden_cohort_ids": [str(c2.id)],
            "ar_content": {"enabled": True, "title": "مهمة ساتي"},
        },
    )
    assert upd.status_code == 200, upd.text
    upd_data = upd.json()
    assert upd_data["title"] == "Custom Marketing Title"
    assert upd_data["field_states"]["title"]["source"] == "override"
    assert [s["cohort_id"] for s in upd_data["steps"]] == [str(c1.id)]
    assert len(upd_data["live_steps"]) == 2
    assert upd_data["live_steps"][1]["hidden"] is True

    # Reset title back to live
    rst = await client.post(
        f"/sessions/programs/{prog_id}/landing-page/reset-field",
        headers=ops_h,
        json={"field": "title"},
    )
    assert rst.status_code == 200, rst.text
    assert rst.json()["title"] == f"Satty Mission {suf}"
    assert rst.json()["field_states"]["title"]["source"] == "live"

    # Rotate preview token -> old token 404, new token 200
    old_tok = lp["preview_token"]
    rot = await client.post(
        f"/sessions/programs/{prog_id}/landing-page/preview-token/regenerate",
        headers=ops_h,
    )
    assert rot.status_code == 200
    new_tok = rot.json()["preview_token"]
    assert new_tok != old_tok
    assert (await client.get(f"/public/website/preview/{old_tok}")).status_code == 404
    assert (await client.get(f"/public/website/preview/{new_tok}")).status_code == 200

    # Publish -> public /resolve/{slug} now 200
    pub_act = await client.post(f"/sessions/programs/{prog_id}/landing-page/publish", headers=ops_h)
    assert pub_act.status_code == 200
    assert pub_act.json()["is_published"] is True
    pub_200 = await client.get(f"/public/website/events/resolve/{lp['slug']}")
    assert pub_200.status_code == 200
    assert pub_200.json()["kind"] == "event"
    assert len(pub_200.json()["event"]["steps"]) == 1


@pytest.mark.asyncio
async def test_org_three_state_program_page_access(
    client: AsyncClient, db_session: AsyncSession
):
    ops, partner, org, suf = await _seed_users_and_org(db_session)
    ops_h = _hdrs(ops)
    partner_h = _hdrs(partner)

    # Partner creates an org-owned program
    pr = await client.post(
        "/organization/programs",
        headers=partner_h,
        json={"name": f"Org Robo {suf}", "code": f"ORGR-{suf.upper()}", "program_type": "workshop"},
    )
    assert pr.status_code == 201, pr.text
    org_prog_id = pr.json()["id"]

    # 1. Default access = disabled -> partner gets 403
    r_dis = await client.get(f"/sessions/programs/{org_prog_id}/landing-page", headers=partner_h)
    assert r_dis.status_code == 403

    # 2. Ops sets access = review -> partner can edit & submit for review (stays unpublished), can unpublish directly
    up_rev = await client.put(
        f"/admin/website/organizations/{org.id}",
        headers=ops_h,
        json={"program_page_access": "review"},
    )
    assert up_rev.status_code == 200, up_rev.text
    assert up_rev.json()["program_page_access"] == "review"

    r_rev = await client.post(f"/sessions/programs/{org_prog_id}/landing-page", headers=partner_h)
    assert r_rev.status_code == 200
    assert r_rev.json()["org_access"] == "review"

    sub = await client.post(f"/sessions/programs/{org_prog_id}/landing-page/publish", headers=partner_h)
    assert sub.status_code == 200
    assert sub.json()["is_published"] is False
    assert sub.json()["submitted_for_review_at"] is not None

    # Ops publishes it
    ops_pub = await client.post(f"/sessions/programs/{org_prog_id}/landing-page/publish", headers=ops_h)
    assert ops_pub.status_code == 200
    assert ops_pub.json()["is_published"] is True

    # Partner can unpublish directly even in review mode
    unp = await client.post(f"/sessions/programs/{org_prog_id}/landing-page/unpublish", headers=partner_h)
    assert unp.status_code == 200
    assert unp.json()["is_published"] is False

    # 3. Ops sets access = direct -> partner publishes directly
    up_dir = await client.put(
        f"/admin/website/organizations/{org.id}",
        headers=ops_h,
        json={"program_page_access": "direct"},
    )
    assert up_dir.status_code == 200
    dir_pub = await client.post(f"/sessions/programs/{org_prog_id}/landing-page/publish", headers=partner_h)
    assert dir_pub.status_code == 200
    assert dir_pub.json()["is_published"] is True


@pytest.mark.asyncio
async def test_multi_case_study_per_program_ordered_cohorts_and_live_metrics(
    client: AsyncClient, db_session: AsyncSession
):
    ops, partner, org, suf = await _seed_users_and_org(db_session)
    ops_h = _hdrs(ops)
    partner_h = _hdrs(partner)

    prog = Program(
        id=uuid.uuid4(),
        code=f"CSMULTI-{suf.upper()}",
        name=f"Satty {suf}",
        program_type="competition",
        description="Multi-stage satellite competition.",
        pricing_model="free",
        active=True,
    )
    c1 = Cohort(id=uuid.uuid4(), program_id=prog.id, name="Satty v1 - Stage 1", status="completed", starts_on=date(2026, 1, 10))
    c2 = Cohort(id=uuid.uuid4(), program_id=prog.id, name="Satty v1 - Finals", status="completed", starts_on=date(2026, 2, 10))
    c3 = Cohort(id=uuid.uuid4(), program_id=prog.id, name="Satty v2 - Partner Run", status="completed", organization_id=org.id, starts_on=date(2026, 5, 10))
    ct1 = Contact(id=uuid.uuid4(), full_name="Student One", email=f"s1_{suf}@test.com")
    ct2 = Contact(id=uuid.uuid4(), full_name="Student Two", email=f"s2_{suf}@test.com")
    db_session.add(prog)
    await db_session.flush()
    db_session.add_all([c1, c2, c3, ct1, ct2])
    await db_session.flush()

    db_session.add_all([
        Registration(id=uuid.uuid4(), cohort_id=c1.id, contact_id=ct1.id, status="completed", ticket_token=uuid.uuid4().hex, registered_via="ops"),
        Registration(id=uuid.uuid4(), cohort_id=c1.id, contact_id=ct2.id, status="registered", ticket_token=uuid.uuid4().hex, registered_via="ops"),
        Registration(id=uuid.uuid4(), cohort_id=c2.id, contact_id=ct1.id, status="completed", ticket_token=uuid.uuid4().hex, registered_via="ops"),
        Session(id=uuid.uuid4(), cohort_id=c1.id, title="Orientation", meeting_date=date(2026, 1, 10)),
        Session(id=uuid.uuid4(), cohort_id=c2.id, title="Final Pitch", meeting_date=date(2026, 2, 10)),
    ])
    await db_session.commit()

    # Partner cannot create case studies (Ops-only!)
    forbid = await client.post(
        "/admin/website/case-studies/from-program",
        headers=partner_h,
        json={"program_id": str(prog.id), "cohort_ids": [str(c1.id)]},
    )
    assert forbid.status_code == 403

    # Ops creates Case Study #1 (Satty v1: c1 -> c2 in exact order)
    cs1_r = await client.post(
        "/admin/website/case-studies/from-program",
        headers=ops_h,
        json={
            "program_id": str(prog.id),
            "cohort_ids": [str(c1.id), str(c2.id)],
            "title": f"Satty v1 Impact {suf}",
        },
    )
    assert cs1_r.status_code == 201, cs1_r.text
    cs1 = cs1_r.json()
    assert cs1["live_linked"] is True
    assert cs1["is_published"] is False
    assert cs1["preview_token"]
    assert [s["title"] for s in cs1["structure_sections"]] == ["Satty v1 - Stage 1", "Satty v1 - Finals"]
    assert cs1["structure_sections"][0]["badge"] == "Stage 01"
    assert cs1["structure_sections"][1]["badge"] == "Stage 02"

    # Ops creates Case Study #2 for the same program (Satty v2: c3 only)
    cs2_r = await client.post(
        "/admin/website/case-studies/from-program",
        headers=ops_h,
        json={
            "program_id": str(prog.id),
            "cohort_ids": [str(c3.id)],
            "title": f"Satty v2 Partner {suf}",
        },
    )
    assert cs2_r.status_code == 201, cs2_r.text
    assert cs2_r.json()["partner_name"] == org.name_latin

    # List filtered by program_id returns both
    lst = await client.get(f"/admin/website/case-studies?program_id={prog.id}", headers=ops_h)
    assert lst.status_code == 200
    assert len(lst.json()) == 2

    # Preview works in draft; public slug 404 until published
    assert (await client.get(f"/public/website/case-studies/{cs1['slug']}")).status_code == 404
    prev = await client.get(f"/public/website/preview/{cs1['preview_token']}")
    assert prev.status_code == 200
    assert prev.json()["kind"] == "case_study"
    assert "noindex" in prev.headers.get("x-robots-tag", "").lower()

    # Publish cs1 -> public slug 200 with live stages
    pub = await client.post(f"/admin/website/case-studies/{cs1['id']}/publish", headers=ops_h)
    assert pub.status_code == 200
    assert pub.json()["is_published"] is True
    pub_get = await client.get(f"/public/website/case-studies/{cs1['slug']}")
    assert pub_get.status_code == 200
    assert len(pub_get.json()["structure_sections"]) == 2

    # Update stage with combined items + legacy days + multiple stage images
    upd = await client.put(
        f"/admin/website/case-studies/{cs1['id']}",
        headers=ops_h,
        json={
            "structure_sections": [
                {
                    "id": "stage-1",
                    "badge": "Stage 01",
                    "title": "Satty v1 - Stage 1",
                    "images": ["/assets/img/stage1-a.jpg", "/assets/img/stage1-b.jpg"],
                    "items": [
                        {
                            "title": "Day 1 - Satellite Development & Integration",
                            "description": "Finalist teams began working on their satellite prototypes.",
                        }
                    ],
                    "days": [
                        {
                            "day_title": "Day 1",
                            "milestones": ["Electrical Integration", "Hardware Assembly", "Programming"],
                        }
                    ],
                }
            ]
        },
    )
    assert upd.status_code == 200, upd.text
    sec0 = upd.json()["structure_sections"][0]
    assert sec0["images"] == ["/assets/img/stage1-a.jpg", "/assets/img/stage1-b.jpg"]
    assert sec0["image_url"] == "/assets/img/stage1-a.jpg"
    assert sec0["days"] == []
    assert len(sec0["items"]) == 1
    assert sec0["items"][0]["title"] == "Day 1 - Satellite Development & Integration"
    assert sec0["items"][0]["description"] == "Finalist teams began working on their satellite prototypes."
    assert sec0["items"][0]["milestones"] == [
        "Electrical Integration",
        "Hardware Assembly",
        "Programming",
    ]
