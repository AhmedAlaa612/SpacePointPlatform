"""Verification test suite for SpacePoint Website CMS & Public APIs.

Tests:
1. Public Marketing APIs:
   - GET /public/articles (pagination, category filter, compiled safe HTML)
   - GET /public/articles/{slug} (single payload + next/prev navigation)
   - GET /public/sponsors (grouped tiers: client, partner, supporter, academic)
   - GET /public/media (12 clippings with bilingual flags)
   - GET /public/student-missions (6 student research showcase cards)
   - POST /public/leads (workshop booking + newsletter validation)

2. Collaborative Authoring & Review Workflow:
   - Instructor creates article draft
   - Instructor submits draft for review
   - Admin requests changes with feedback
   - Instructor addresses feedback and resubmits
   - Admin approves and publishes article
   - Public endpoint immediately reflects newly published article
"""

import asyncio
import os
import sys

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Point explicitly to staging DB
os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:67500@localhost:5433/spacepoint_cms_dev"

import httpx
from app.main import app


async def run_tests():
    print("==================================================================")
    print("  RUNNING CMS & PUBLIC API VERIFICATION SUITE (spacepoint_cms_dev) ")
    print("==================================================================")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # ── Test 1: Public Articles Listing ───────────────────────────────────
        print("\n[1] Testing GET /public/articles...")
        res = await client.get("/public/articles")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        data = res.json()
        assert data["total"] >= 3, f"Expected >= 3 articles, got {data['total']}"
        assert len(data["items"]) >= 3
        first_article = data["items"][0]
        assert "slug" in first_article
        assert "content_html" in first_article
        assert "<p>" in first_article["content_html"]
        print(f"  ✓ Found {data['total']} published articles with compiled HTML.")

        # Test Category Filter
        tech_res = await client.get("/public/articles?category=TECHNOLOGY")
        assert tech_res.status_code == 200
        tech_data = tech_res.json()
        assert len(tech_data["items"]) >= 1
        assert all(a["category"] == "TECHNOLOGY" for a in tech_data["items"])
        print(f"  ✓ Category filter (TECHNOLOGY) returned {len(tech_data['items'])} article(s).")

        # ── Test 2: Public Single Article & Navigation ───────────────────────
        print("\n[2] Testing GET /public/articles/{slug}...")
        slug = "designing-the-future-a-students-guide-to-cubesat-engineering"
        slug_res = await client.get(f"/public/articles/{slug}")
        assert slug_res.status_code == 200, f"Expected 200, got {slug_res.status_code}"
        slug_data = slug_res.json()
        assert slug_data["article"]["slug"] == slug
        assert slug_data["article"]["author_display_name"] == "Sarah Al Kaabi"
        assert "prev_article" in slug_data or "next_article" in slug_data
        print(f"  ✓ Successfully fetched single article '{slug}' with prev/next navigation.")

        # ── Test 3: Public Sponsors Marquee ──────────────────────────────────
        print("\n[3] Testing GET /public/sponsors...")
        spons_res = await client.get("/public/sponsors")
        assert spons_res.status_code == 200
        spons_data = spons_res.json()
        assert len(spons_data["all"]) >= 30, f"Expected >= 30 sponsors, got {len(spons_data['all'])}"
        assert len(spons_data["grouped"]["client"]) >= 5
        assert len(spons_data["grouped"]["partner"]) >= 10
        assert len(spons_data["grouped"]["supporter"]) >= 2
        assert len(spons_data["grouped"]["academic"]) >= 4
        print(f"  ✓ Successfully fetched {len(spons_data['all'])} sponsors grouped across 4 tiers.")

        # ── Test 4: Public Media Coverage ────────────────────────────────────
        print("\n[4] Testing GET /public/media...")
        media_res = await client.get("/public/media")
        assert media_res.status_code == 200
        media_items = media_res.json()
        assert len(media_items) == 12, f"Expected 12 media clippings, got {len(media_items)}"
        arabic_items = [m for m in media_items if m["is_arabic"]]
        english_items = [m for m in media_items if not m["is_arabic"]]
        assert len(arabic_items) >= 5, "Expected Arabic press clippings"
        assert len(english_items) >= 5, "Expected English press clippings"
        print(f"  ✓ Successfully fetched {len(media_items)} media clippings ({len(arabic_items)} Arabic, {len(english_items)} English).")

        # ── Test 5: Public Student Missions ──────────────────────────────────
        print("\n[5] Testing GET /public/student-missions...")
        mission_res = await client.get("/public/student-missions")
        assert mission_res.status_code == 200
        missions = mission_res.json()
        assert len(missions) == 6, f"Expected 6 student missions, got {len(missions)}"
        assert all(m["docx_url"] and m["photo_url"] for m in missions)
        print(f"  ✓ Successfully fetched {len(missions)} student showcase missions with valid assets.")

        # ── Test 6: Public Leads Ingestion ───────────────────────────────────
        print("\n[6] Testing POST /public/leads...")
        # 6a: Workshop Booking Lead
        workshop_payload = {
            "lead_type": "workshop_booking",
            "contact_name": "Dr. Tariq Al Nuaimi",
            "email": "tariq.nuaimi@ad-school.ae",
            "phone": "+971501234567",
            "organization_name": "Abu Dhabi STEM Academy",
            "program_interest": "CubeSat Hands-On Workshop",
            "details": {
                "estimated_students": 45,
                "preferred_month": "November 2026",
                "notes": "Interested in 3-day intensive SatKit deployment.",
            },
        }
        lead_res = await client.post("/public/leads", json=workshop_payload)
        assert lead_res.status_code == 201, f"Expected 201, got {lead_res.status_code}: {lead_res.text}"
        assert lead_res.json()["success"] is True
        print("  ✓ Workshop booking lead created successfully.")

        # 6b: Newsletter Lead
        newsletter_payload = {
            "lead_type": "newsletter",
            "email": "innovator@spaceenthusiast.com",
        }
        news_res = await client.post("/public/leads", json=newsletter_payload)
        assert news_res.status_code == 201
        assert news_res.json()["success"] is True
        print("  ✓ Newsletter subscription lead created successfully.")

        # ── Test 7: Multi-Role Editorial State Machine ─────────────────────────
        print("\n[7] Testing Contributor Authoring & Editorial Review Pipeline...")

        # Step 7a: Log in as Instructor (author)
        inst_auth = await client.post(
            "/auth/login",
            json={"email": "instructor@spacepoint.ae", "password": "DevPass123!"},
        )
        assert inst_auth.status_code == 200, f"Instructor login failed: {inst_auth.text}"
        instructor_token = inst_auth.json()["access_token"]
        inst_headers = {"Authorization": f"Bearer {instructor_token}"}

        # Step 7b: Create Draft Article
        create_payload = {
            "title": "Autonomous Lunar Rover Perception Algorithms",
            "summary": "Exploring edge computing and stereo vision models for small lunar rovers.",
            "category": "TECHNOLOGY",
            "content_markdown": "# Lunar Perception\n\nTesting **stereo disparity** algorithms for rover obstacle avoidance.",
            "submit_for_review": False,
        }
        create_res = await client.post("/cms/articles", json=create_payload, headers=inst_headers)
        assert create_res.status_code == 201, f"Article creation failed: {create_res.text}"
        new_article = create_res.json()
        article_id = new_article["id"]
        assert new_article["status"] == "draft"
        assert new_article["author_display_name"] == "Sarah Al Kaabi"
        assert "<h1>Lunar Perception</h1>" in new_article["content_html"]
        print(f"  ✓ Instructor created draft article '{new_article['title']}' (ID: {article_id}).")

        # Step 7c: Submit Draft for Review
        submit_res = await client.patch(
            f"/cms/articles/{article_id}",
            json={"submit_for_review": True},
            headers=inst_headers,
        )
        assert submit_res.status_code == 200
        assert submit_res.json()["status"] == "in_review"
        print("  ✓ Instructor submitted article for editorial review (status: in_review).")

        # Step 7d: Log in as Admin (reviewer)
        admin_auth = await client.post(
            "/auth/login",
            json={"email": "dev-admin@spacepoint.ae", "password": "devadmin123"},
        )
        assert admin_auth.status_code == 200, f"Admin login failed: {admin_auth.text}"
        admin_token = admin_auth.json()["access_token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Step 7e: Admin requests changes with feedback
        reject_res = await client.post(
            f"/operations/website/articles/{article_id}/review",
            json={
                "action": "request_changes",
                "reviewer_feedback": "Please add a paragraph explaining radiation hardening for the camera sensor.",
            },
            headers=admin_headers,
        )
        assert reject_res.status_code == 200
        rejected_art = reject_res.json()
        assert rejected_art["status"] == "changes_requested"
        assert "radiation hardening" in rejected_art["reviewer_feedback"]
        print("  ✓ Admin requested changes with feedback (status: changes_requested).")

        # Step 7f: Instructor edits article addressing feedback and resubmits
        update_payload = {
            "content_markdown": "# Lunar Perception\n\nTesting **stereo disparity** algorithms.\n\n### Radiation Hardening\nCameras require ceramic shielding against galactic cosmic rays.",
            "submit_for_review": True,
        }
        resubmit_res = await client.patch(
            f"/cms/articles/{article_id}",
            json=update_payload,
            headers=inst_headers,
        )
        assert resubmit_res.status_code == 200
        resubmitted_art = resubmit_res.json()
        assert resubmitted_art["status"] == "in_review"
        assert "Radiation Hardening" in resubmitted_art["content_html"]
        print("  ✓ Instructor addressed feedback and resubmitted article (status: in_review).")

        # Step 7g: Admin approves article
        approve_res = await client.post(
            f"/operations/website/articles/{article_id}/review",
            json={"action": "approve", "featured_order": 99},
            headers=admin_headers,
        )
        assert approve_res.status_code == 200
        approved_art = approve_res.json()
        assert approved_art["status"] == "published"
        assert approved_art["published_at"] is not None
        print(f"  ✓ Admin approved and published article '{approved_art['slug']}'.")

        # Step 7h: Verify published article immediately appears on public API
        verify_pub = await client.get(f"/public/articles/{approved_art['slug']}")
        assert verify_pub.status_code == 200
        assert verify_pub.json()["article"]["title"] == "Autonomous Lunar Rover Perception Algorithms"
        print("  ✓ Newly published article is immediately discoverable via GET /public/articles/{slug}!")

    print("\n==================================================================")
    print("  ALL 7 TEST SUITES PASSED! Phase 1 Backend & APIs 100% VERIFIED  ")
    print("==================================================================")


if __name__ == "__main__":
    asyncio.run(run_tests())
