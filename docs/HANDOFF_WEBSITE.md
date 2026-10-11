# Website, Store & SpacePoint Labs Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

> **Status:** Verified **2026-10-11** against live production deployment (`https://portal.spacepoint.ae`, `https://spacepoint.ae`, `https://labs.spacepoint.ae`) and Alembic head `c7d3e1f9a2b5`.

The Website & Public CMS domain powers SpacePoint's public marketing website (`https://spacepoint.ae`), the interactive SpacePoint Labs showcase (`https://labs.spacepoint.ae`), and the e-commerce merchandise store (Stripe Checkout), all managed centrally from the SpacePoint Portal (`https://portal.spacepoint.ae`).

---

## 1. Three-Repository Architecture

| Repository | Live Domain | VPS Path | Deploy Script | Role |
|---|---|---|---|---|
| `AhmedAlaa612/spacepoint-stripe-test` | `https://portal.spacepoint.ae` | Docker (`spacepoint-api`) + `/var/www/spacepoint-unified/dist` | `deploy-backend.sh`<br/>`deploy-frontend.sh` | FastAPI backend (`/public/*`, `/admin/website/*`, `/admin/store/*`) + Portal CMS UI (`/admin/website`, `/operations/inventory/website`, `/operations/inventory/shop`) |
| `AhmedAlaa612/spacepoint-website` | `https://spacepoint.ae` | `/var/www/spacepoint-website-repo` → `/var/www/spacepoint-website/dist` | `deploy-website.sh` | Astro 5 + React Islands static site (`output: "static"`) with build-time SSG + live client-side hydration from `https://portal.spacepoint.ae/api/public/*` |
| `AhmedAlaa612/spacepoint-labs` | `https://labs.spacepoint.ae` | `/var/www/spacepoint-labs` | `deploy-labs.sh` | Pure static HTML/CSS/Three.js showcase fetching live project cards from `https://portal.spacepoint.ae/api/public/labs/projects` |

### How Updates Flow to the Public Sites
1. **Live Client-Side Hydration (Immediate — No Rebuild Needed):**
   - `spacepoint.ae` pages include inline hydration scripts and React islands that fetch live data from `https://portal.spacepoint.ae/api/public/*` on page load:
     - Home (`/`): impact counters (`students_count`, `workshops_count`, `partners_count`), FAQ contact email, and 3-tier sponsor/partner marquees (`clients`, `partners`, `supporters`).
     - Footer & Navbar (all pages): social links (`instagram_url`, `linkedin_url`, `tiktok_url`, `youtube_url`), `contact_email`, `contact_phone`, `location_address`, and store visibility toggle (`store_visible`).
     - Programs (`/programs`), Resources (`/resources`), Media Coverage (`/media-coverage`), Blog (`/blog`), Shop (`/shop`), Team (`/team`), Ambassadors (`/ambassadors`), Alumni (`/alumni`), and Student Missions (`/student-missions`).
   - `labs.spacepoint.ae` fetches `GET https://portal.spacepoint.ae/api/public/labs/projects` on load and renders the project grid dynamically.
2. **Static Site Generation (SSG Fallback at Build Time):**
   - Running `deploy-website.sh` on the VPS runs `astro build`, which calls `src/lib/api.ts` against `https://portal.spacepoint.ae/api` to bake the latest database content into the static HTML for SEO and instant initial paint, including newly created `/blog/[slug]` routes.

---

## 2. Roles, Permissions & Portal Navigation

All Website CMS and Store management endpoints use `Depends(require_operations)` (`backend/app/core/dependencies.py`), which permits:
- **`admin`** (passes all role guards unconditionally)
- **`operations`**

### Portal Routes (`frontend/src/router.tsx` & `Sidebar.tsx`)
- **Admin Sidebar:**
  - `/admin/website` → `WebsiteManagement.tsx`
  - `/admin/shop` → `Shop.tsx`
- **Operations Sidebar (under the `Inventory` group):**
  - `/operations/inventory/website` → `WebsiteManagement.tsx`
  - `/operations/inventory/shop` → `Shop.tsx`

---

## 3. Portal CMS Tabs (`WebsiteManagement.tsx`)

`frontend/src/pages/admin/WebsiteManagement.tsx` organizes all website management into 12 tabs:

| Tab ID | Label | Backing Table(s) | Key Capabilities |
|---|---|---|---|
| `leads` | **Inquiries & Bookings** | `website_leads` | Filter by type (`inquiry` vs `workshop_booking`) and status (`new`, `contacted`, `qualified`, `closed`), inspect `details` JSON, update status/notes, delete |
| `newsletter` | **Newsletter** | `newsletter_subscribers` | Search subscribers, toggle active/unsubscribed, **Export Active CSV**, delete |
| `articles` | **Blog & Insights** | `website_articles` | Create/edit/delete articles, upload cover image (`POST /admin/website/upload-image`), manage `content_html` + `tags`, toggle `is_featured` / `is_published` |
| `press` | **Press & Media** | `press_mentions` | Manage media outlets, logos, external article URLs, publish dates, featured status, sort order |
| `programs` | **Programs** | `website_programs` | Manage flagship programs (`kind="flagship"`) and specialized workshops (`kind="workshop"`), badges, specs, tags, deliverables, cover images |
| `missions` | **Student Missions** | `student_missions` | Manage student mission cards, mission badges, dates, status, locations, cover images |
| `labs` | **Labs Projects** | `labs_projects` | Manage SpacePoint Labs hardware/software R&D cards (`labs.spacepoint.ae`), status (`Released`, `R&D`, `Prototype`), tags, cover images, external URLs |
| `team` | **Team** | `team_members` | Manage leadership (`category="leadership"`) and advisors (`category="advisor"`), roles, bios, LinkedIn/email links, photos |
| `ambassadors` | **Ambassadors** | `website_ambassadors` | Manage public website ambassador spotlight cards (distinct from the internal Ambassadors portal accounts), roles, bios, social links, photos |
| `alumni` | **Alumni** | `alumni_members` | Manage alumni network cards, cohort badges, current roles/organizations, achievements, LinkedIn links, photos |
| `sponsors` | **Sponsors & Partners** | `sponsors_partners` | Manage marquee logos across tiers (`clients`, `partners`, `supporters`), upload logos, reorder, toggle active |
| `faqs` | **FAQs & Config** | `website_faqs`<br/>`website_config` | CRUD FAQs + edit global Website Settings (Impact counters: Students Trained, Workshops Delivered, Partner Institutions; Contact info; Social Media URLs; Store visibility toggle) |

---

## 4. Store & Merchandise (`Shop.tsx`)

Managed at `/admin/shop` and `/operations/inventory/shop` (`frontend/src/pages/admin/Shop.tsx`):
- **Products (`store_products`):** Name, slug, category, price (`price_aed`), stock quantity, cover + gallery images (`POST /admin/store/upload-image`), sizes/variants, active/featured toggles.
- **Orders (`store_orders` & `store_order_items`):** Stripe Checkout integration (`POST /public/store/checkout` + Stripe webhook), customer details, shipping address, order status (`pending`, `paid`, `processing`, `shipped`, `delivered`, `cancelled`), fulfilment tracking.
- **Discount Codes (`discount_codes`):** Percentage or fixed AED discounts, usage limits, expiry dates, active toggle.
- **Global Store Visibility:** Controlled by `WebsiteConfig.store_visible` (toggled either from `Shop.tsx` header or `WebsiteManagement.tsx` → `FAQs & Config`). When `false`, `/shop` links in `spacepoint.ae` Navbar/Footer are hidden and `/shop` displays a "Store Coming Soon" state.

---

## 5. Backend Routers, Models & Database Tables

### Backend Files
| Component | Path |
|---|---|
| **Public CMS & Leads Router** | `backend/app/routers/public_content.py` (`/public/*`) |
| **Public Website Extensions Router** | `backend/app/routers/public_website.py` (`/public/website/*`, `/public/labs/*`) |
| **Public Store & Checkout Router** | `backend/app/routers/public_store.py` (`/public/store/*`) |
| **Admin CMS Router** | `backend/app/routers/admin/website.py` (`/admin/website/*`) |
| **Admin Website Config & Programs Router** | `backend/app/routers/admin/website_config.py` (`/admin/website/*`) |
| **Admin People & Labs Router** | `backend/app/routers/admin/website_people.py` (`/admin/website/*`) |
| **Admin Store Router** | `backend/app/routers/admin/store.py` (`/admin/store/*`) |
| **CMS Models** | `backend/app/models/website_cms.py` |
| **Config, Programs & Resources Models** | `backend/app/models/website_config.py` |
| **Labs, Team, Ambassadors, Alumni, Missions Models** | `backend/app/models/website_people.py` |
| **Store Models** | `backend/app/models/store.py` |

### Migrations & Seeding (`backend/alembic/versions/`)
All website and store tables are created and idempotently seeded via Alembic migrations (`WHERE NOT EXISTS` guards so re-running or migrating an existing database never duplicates rows):
1. `e1f2a3b4c5d6_store_tables.py` — creates `store_products`, `store_orders`, `store_order_items`, `discount_codes`.
2. `f3a4b5c6d7e8_website_cms_tables.py` — creates `website_leads`, `newsletter_subscribers`, `website_articles`, `press_mentions`, `sponsors_partners`, `website_faqs`.
3. `a5b6c7d8e9f0_website_config_programs_resources.py` — creates `website_config`, `website_programs`, `website_resources`.
4. `b6c7d8e9f0a1_website_people.py` — creates `labs_projects`, `team_members`, `website_ambassadors`, `alumni_members`, `student_missions` and seeds all baseline website content. *(Note: `NULL::jsonb` explicit cast is required in PostgreSQL `VALUES` clauses for `metrics_json`).*
5. `c7d3e1f9a2b5_seed_store_products.py` — seeds the 5 baseline SpacePoint merchandise products into `store_products`.

---

## 6. Key Operational Mechanics & Gotchas

### 1. Lead Submission Email Forwarding (`POST /public/leads`)
When a visitor submits the Contact Inquiry form (`/contact`) or Workshop Booking form (`/book-workshop`) on `spacepoint.ae`:
- `POST /public/leads` (`backend/app/routers/public_content.py`) saves the `WebsiteLead` row in PostgreSQL.
- It then queries `WebsiteConfig` (`id=1`) for `contact_email` (defaulting to `info@spacepoint.ae`) and calls `send_email(...)` (`backend/app/services/email.py`) with a formatted HTML table of the inquiry/booking details.
- Email errors are caught and logged (`logger.warning`) so a transient Resend/SMTP issue never causes the user's form submission to fail with a `500`.

### 2. Image Uploads & `WEBSITE_BASE_URL` Resolution
- **Uploaded images** (`POST /admin/website/upload-image` and `POST /admin/store/upload-image`) are stored in the public storage bucket `website-assets` (`PUBLIC_BUCKETS = {"website-assets"}` in `backend/app/routers/files.py`), which serves `/files/website-assets/{path}` **without** requiring an expiring HMAC signature.
- **Seeded static assets** use site-relative paths like `/assets/img/team/sultan.jpg` or `/assets/img/merch/polo.png`, which live inside `spacepoint-website/public/assets/img/`.
- Because the Portal runs on `https://portal.spacepoint.ae` while static website assets live on `https://spacepoint.ae`, both `WebsiteManagement.tsx` and `Shop.tsx` use `resolveImg(url)`:
  - Any path starting with `/assets/` is prefixed with `WEBSITE_BASE_URL` (`import.meta.env.VITE_WEBSITE_URL`, which defaults to `"https://spacepoint.ae"` in production and is set in `.github/workflows/build-frontend.yml`).
  - Any path starting with `/files/` is prefixed with the API host (`https://portal.spacepoint.ae`).

### 3. `PUBLIC_API_URL` & Avoiding the `localhost:8000` Trap
- `spacepoint-website` has a local `.env` with `PUBLIC_API_URL=http://localhost:8000` for local dev.
- On the VPS, `/var/www/spacepoint-website-repo/.env` must be set to:
  ```env
  PUBLIC_API_URL=https://portal.spacepoint.ae/api
  ```
- As an additional safeguard in code (`src/layouts/BaseLayout.astro`, `src/components/Footer.astro`, and `src/lib/api.ts`), any `PUBLIC_API_URL` containing `localhost` or `127.0.0.1` is **automatically ignored** during `astro build` (`import.meta.env.PROD`) and whenever `window.location.hostname` is not `localhost` / `127.0.0.1`, falling back to `"https://portal.spacepoint.ae/api"`.

### 4. Cross-Origin Resource Sharing (CORS)
Because `https://spacepoint.ae` and `https://labs.spacepoint.ae` make browser `fetch()` requests directly to `https://portal.spacepoint.ae/api/public/*`:
- `backend/app/main.py` configures `CORSMiddleware` with:
  ```python
  allow_origin_regex=r"^https?://([a-z0-9-]+\.)?spacepoint\.ae$"
  ```
- This guarantees that `spacepoint.ae`, `www.spacepoint.ae`, `labs.spacepoint.ae`, `portal.spacepoint.ae`, and `lms.spacepoint.ae` are always permitted by CORS even if `/etc/spacepoint/env`'s `CORS_ORIGINS` only lists `portal` and `lms`.

### 5. Website Config Auto-Heal (`_get_or_seed`)
Both `GET /admin/website/config` (`backend/app/routers/admin/website_config.py`) and `GET /public/website/config` (`backend/app/routers/public_website.py`) use `_get_or_seed(db)`:
- If row `id=1` in `website_settings` does not exist, it creates it with production defaults (`2,700+` students, `40+` workshops, `25` partners, `info@spacepoint.ae`, social URLs).
- If row `id=1` exists with empty strings `""` (from an older unseeded creation), `_get_or_seed` automatically backfills the empty fields with the production defaults.
