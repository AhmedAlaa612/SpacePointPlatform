# SpacePoint CMS & Public Website API Architecture

## 1. Executive Summary
This document outlines the shared architecture connecting the **Unified SpacePoint Portal & LMS** (`spacepoint-stripe-test`) with the standalone **Astro 5 Public Website** (`spacepoint-website`).

Previously, website content was hardcoded across legacy static HTML pages with Google Forms iframes and unauthenticated admin scripts. The modernized system replaces this with:
1. **Shared PostgreSQL Domain Models**: Stored in the unified schema with full relational integrity and audit trails.
2. **Multi-Role Editorial Workflows**: Interns, instructors, and facilitators author articles in the portal (`/articles`), while administrators review, provide structured revision feedback, and publish.
3. **Operations Suite**: Portal administrators manage sponsors, student mission showcases, press clippings, and incoming website leads from a unified operations dashboard (`/operations/website`).
4. **Public REST APIs**: High-performance, unauthenticated endpoints with caching headers consumed by Astro 5 SSG at build time and React Islands on the client.

---

## 2. Shared Data Models

All models inherit from `app.models.base.BaseModel` (providing `id`, `created_at`, `updated_at`):

### `Article` (`articles`)
- `title` (VARCHAR 255): Article title
- `slug` (VARCHAR 255, UNIQUE): URL-friendly identifier
- `summary` (TEXT): Subtitle/abstract
- `content_markdown` (TEXT): Raw markdown authored by contributor
- `content_html` (TEXT): Sanitized HTML rendered at submission
- `category` (VARCHAR 64): E.g. `EDUCATION`, `TECHNOLOGY`, `SCIENCE`, `COMMUNITY`
- `cover_image_url` (VARCHAR 512): Cover image asset
- `status` (ENUM `ArticleStatus`): `draft`, `submitted`, `in_review`, `changes_requested`, `published`, `archived`
- `author_id` (UUID FK `users.id`): Creator
- `reviewer_id` (UUID FK `users.id`, NULLABLE): Admin reviewer
- `reviewer_feedback` (TEXT, NULLABLE): Actionable critique when returning for revisions
- `published_at` (TIMESTAMP WITH TZ, NULLABLE)
- `featured_order` (INTEGER, DEFAULT 0)

### `Sponsor` (`sponsors`)
- `name` (VARCHAR 255): Organization name
- `logo_url` (VARCHAR 512): High-resolution logo
- `website_url` (VARCHAR 512, NULLABLE)
- `tier` (ENUM `SponsorTier`): `client`, `partner`, `supporter`, `academic`
- `display_order` (INTEGER)
- `is_active` (BOOLEAN)

### `StudentMission` (`student_missions`)
- `student_name` (VARCHAR 255): Student researcher name
- `project_title` (VARCHAR 255): E.g. "LoRa-Based Satellite Dashboard"
- `category` (VARCHAR 128): E.g. "Embedded Systems"
- `description` (TEXT): Project abstract
- `docx_url` (VARCHAR 512, NULLABLE): Downloadable project report
- `photo_url` (VARCHAR 512, NULLABLE): Project hardware photo
- `metrics_json` (JSONB, NULLABLE): Key performance indicators (e.g. `{"Altitude": "32,400m"}`)
- `display_order` (INTEGER)
- `is_active` (BOOLEAN)

### `MediaClipping` (`media_clippings`)
- `publisher_name` (VARCHAR 255): E.g. "Gulf News", "WAM"
- `article_title` (VARCHAR 255): News headline
- `article_url` (VARCHAR 512): Source URL
- `published_date` (DATE)
- `logo_url` (VARCHAR 512, NULLABLE): Media outlet badge
- `is_arabic` (BOOLEAN, DEFAULT FALSE): For RTL text display
- `snippet` (TEXT, NULLABLE): Summary excerpt
- `display_order` (INTEGER)
- `is_active` (BOOLEAN)

### `WebsiteLead` (`website_leads`)
- `lead_type` (ENUM `LeadType`): `workshop_booking`, `newsletter`, `inquiry`
- `contact_name` (VARCHAR 255, NULLABLE)
- `email` (VARCHAR 255)
- `phone` (VARCHAR 64, NULLABLE)
- `organization_name` (VARCHAR 255, NULLABLE)
- `program_interest` (VARCHAR 128, NULLABLE)
- `details` (JSONB): Form payload (e.g. student count, preferred dates)
- `status` (ENUM `LeadStatus`): `new`, `contacted`, `converted`, `archived`

---

## 3. Public API Endpoints (`/public/*`)

| Endpoint | Method | Description |
|---|---|---|
| `/public/articles` | `GET` | List published articles (supports `?category=...&limit=...`) |
| `/public/articles/{slug}` | `GET` | Retrieve single published article by URL slug |
| `/public/sponsors` | `GET` | Grouped sponsors by tier (`clients`, `partners`, `supporters`, `academic`) |
| `/public/student-missions` | `GET` | List active student research projects and missions |
| `/public/media` | `GET` | List press media clippings ordered by display priority |
| `/public/leads` | `POST` | Inbound intake for workshop bookings, newsletters, and contact inquiries |

---

## 4. Admin API Endpoints (`/admin/website/*`)

All admin routes require active administrative authorization (`require_roles(["ADMIN"])`).

| Endpoint | Method | Description |
|---|---|---|
| `/admin/website/articles` | `GET`, `POST` | List all articles across statuses; create admin article |
| `/admin/website/articles/{id}/review` | `POST` | Approve, reject (with feedback), or request changes |
| `/admin/website/articles/{id}/publish` | `POST` | Publish approved article to live website |
| `/admin/website/articles/{id}/unpublish` | `POST` | Revert published article to draft status |
| `/admin/website/sponsors` | `GET`, `POST`, `PUT`, `DELETE` | CRUD operations for sponsor ticker |
| `/admin/website/student-missions` | `GET`, `POST`, `PUT`, `DELETE` | Manage student mission showcase items |
| `/admin/website/media` | `GET`, `POST`, `PUT`, `DELETE` | Manage press clippings and external coverage |
| `/admin/website/leads` | `GET`, `PUT` | Manage incoming leads CRM and update pipeline status |
