# Location / City / Country Cleanup — Changelog (2026-08-08)

Recurring bug being fixed: Location forms took a free-typed `country` and never let
anyone set the venue's maps link, so cohort quick-add and all student/instructor-facing
surfaces showed a bare city name with no address and no way to navigate. Fix: `City`
is the anchor for `Location`; `country` is a derived display value (read-only from the
city) and **never entered anywhere**; one canonical resolver builds the full venue
block (name, address, city, country, maps link) for every consumer. Second act
(2026-08-08): country everywhere "opens" the city — every picker is now gated to the
selected country, and countries with no SpacePoint city get an **"Other (type it)"**
free-text option instead of an empty/missing field.

---

## 1. Database migrations (applied to dev DB + test DB)

- `backend/alembic/versions/a1b2c3d4e5f6_cities.py` — cities table + 8 seeded UAE
  cities (Dubai, Abu Dhabi, Sharjah, Al Ain, Ajman, Umm Al Quwain, Fujairah,
  Ras Al Khaimah); backfills + drops applicant profiles' old free-text city columns.
- `backend/alembic/versions/c9d1e2f3a4b5_locations_backfill_city_id.py`
  — backfills `locations.city_id` where the location name exactly matches a seeded
  city name in the same country. Verified: Abu Dhabi, Al Ain, Dubai, Sharjah + the
  inline quick-add site got linked; "Egypt" / "Main Warehouse" stay unlinked, as
  intended (ops links them by hand in the UI).
- `backend/alembic/versions/d1e2f3a4b5c6_soft_deprecate_locations_country.py` — drops
  `NOT NULL` on `locations.country` (values kept; see Phase 3 note).
- `backend/alembic/versions/e1f2a3b4c5d6_add_applications_city_id.py` — `applications.city_id`
  (FK → `cities`, nullable).
- `backend/alembic/versions/f0a1b2c3d4e5_add_users_city_other.py` — `users.city_other`
  (free-text fallback for countries with no SpacePoint city).

Migration chain: `3f4f7d1237e1` → `a1b2c3d4e5f6` → `c9d1e2f3a4b5` → `d1e2f3a4b5c6`
→ `e1f2a3b4c5d6` → `f0a1b2c3d4e5`.

## 2. Backend — model / schema / API

- **Model** `backend/app/models/inventory/location.py` — `country` now nullable and
  marked legacy/derived; `city_id` is the source of truth.
- **Schemas** (`backend/app/schemas/inventory/catalog.py`)
  - `LocationCreate`: `country` removed, `city_id` required.
  - `LocationUpdate`: `country` removed.
  - `LocationOut.country` → `str | None` (derived from city).
- **Router** (`backend/app/routers/inventory/catalog.py`)
  - `_location_out` derives `country` from the linked city.
  - Create validates the city (404 if unknown); update re-derives country when the
    city changes; list ordering puts "no country" rows last.

## 3. Backend — canonical location resolver

- `backend/app/services/sessions/staffing.py::resolve_session_location_display(db, session=None, cohort=None)`
  - The only place allowed to read legacy `cohort.location` / `cohort.location_map_url`.
  - Returns `{name, address, city_name, country, maps_url}`.
- Used at every student/instructor-facing call site (no more per-site string building):
  - Cohort **assignment email** + **call-invite email** (tasks + `services/email.py` new
    `location_address` / `location_maps_url` args).
  - `GET /sessions/available`, `GET /sessions/mine` — new `location_address` /
    `location_maps_url` on the response.
  - `select_instructors` notification & `assign_instructor` notification.
  - `GET /sessions/delivery/today` style surfaces — `SessionDeliveryOut` has
    `location_address` / `location_maps_url`.
  - **Ticket page + ticket email** — `PublicTicketOut` has `location_address` /
    `location_maps_url`; the email body now includes the address and a real maps link.
  - **Public catalog** (`GET /public/catalog`) keeps inline resolution (batch fetch
    avoids N+1) — documented exception, do not "fix" into a loop.
  - Calendar events, payment-letter snapshot, completion-certificate snapshot.
- Busybox grep verified: no other code reads `cohort.location` / `location_map_url`.

## 4. Frontend — forms now city-first, no country entry

- `frontend/src/api/inventory/index.ts` — `createLocationApi` body is
  `{name, city_id, notes?, address?, maps_url?}`.
- `frontend/src/types/inventory.ts` — `Location.country: string | null`.
- `frontend/src/pages/operations/inventory/Catalog.tsx`
  - `LocationModal` rewritten: city is required (submit gated), country is derived +
    read-only, address + maps link preserved on edit.
  - `CityModal` country input → shared `<CountrySelect valueType="code">`.
  - Location list handles a null country.
- `frontend/src/pages/admin/Cohorts.tsx` — quick-add "➕ New location" =
  name + required City + Address + Maps link (no country input).
- Renderers now show address + maps link (ExternalLink icon): `MySessions.tsx`,
  `SessionDetail.tsx`, `AvailableSessions.tsx`, `Ticket.tsx`, `UpcomingProgramRow.tsx`,
  `Calendar.tsx`, `ThisWeek.tsx`.

## 5. Country-gated city pickers + "Other (type it)" everywhere

- `frontend/src/components/ui/CitySelect.tsx` — shared city `<select>`, filtered to
  the selected country (accepts the country as either ISO code "AE" or display name
  "United Arab Emirates"), exports `useCitiesForCountry()` for layout gating, and the
  `CITY_OTHER` option that reveals a free-text input. If a country has no SpacePoint
  cities, the picker shows just the Other option (no empty/confusing state).
- Gated into: `LearnSignup.tsx` (signup), `LearnProfile.tsx` (student profile),
  `Profile.tsx` (instructor city of residence — deliver-cities checklist stays strict,
  it drives staffing matching), `ApplyFlow.tsx` (intern/ambassador/teacher/facilitator
  — country field was a **plain text input**, now `CountrySelect` + gated city).
- `ApplyFlow` stores a typed Other city inside the application's `answers` JSON
  (`city_other`) — no schema change there; approval carries it onto the user.
- Frontend type updates: `User` gains `city_other` (`frontend/src/types/shared.ts`),
  `updateMeApi`/`signup` accept `city_other` (`frontend/src/api/auth.ts`),
  `ApplicationOut` gains `city` (`frontend/src/api/apply.ts`); admin application sheet
  shows City next to Country (`frontend/src/pages/admin/Applications.tsx`).
- Backend for the free-text city: `users.city_other` (model + schemas + `/auth/signup`,
  `/auth/me` PATCH, `/auth/me GET`); signup gap-fills the CRM contact's free-text city
  with the typed name; `GET /admin/applications*` resolves `city` from `city_id`
  (falling back to `answers.city_other`); approving an application copies
  `answers.city_other` onto `users.city_other`.
- New tests: `backend/tests/routers/apply/test_apply_city.py` (apply stores city,
  rejects unknown/garbage city_id, admin resolves its name) + signup city_other
  round-trip in `tests/routers/lms/test_lms_signup.py`.

## 6. Small behavior fixes (this session)

- `frontend/src/lib/countries.ts` — country picker order: **UAE first, Egypt second,
  then all other countries alphabetically** (pinned order, applied everywhere).
- `frontend/src/pages/admin/Cohorts.tsx` — the "Warehouse (optional)" dropdown was
  filtered by the selected location and could come up empty. It now lists **all**
  warehouses, pick any or leave unset; removed the "resolves automatically"
  wording/behavior from the form.

## 7. Tests + verification

- Backend: `pytest tests` → **805 passed** (7 previously errored tests were
  Redis-down at setup; Redis is now installed in WSL and startable with
  `wsl -e sudo service redis-server start`). Test DB caught up via
  `alembic upgrade head` with `DATABASE_URL_TEST`.
- Frontend: `npm run typecheck` clean after every change.

## 8. To run locally

- Backend: `cd backend` then `.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000` (plain, no `--reload`).
- Frontend: `cd frontend` then `npm run dev` → `localhost:5173` (Vite binds
  localhost, not 127.0.0.1; `/api/*` is proxied to the backend).
- Redis (for ARQ jobs): `wsl -e sudo service redis-server start`.

## 9. Deploying to production

Deploy runs `alembic upgrade head` before uvicorn binds (the health check polls up to
120 s). All migrations are additive; the cities table arrives **seeded** (8 UAE
cities hardcoded in the migration), locations named exactly like a seeded city
auto-link, and old free-text `country` columns are never dropped. The only existing
data touched: `applicant_profiles` old `city_of_residence`/`deliver_cities` strings are
backfilled to linked cities and the string columns dropped — snapshot
`SELECT user_id, city_of_residence, deliver_cities FROM applicant_profiles;` before
pushing if you want those strings preserved ever after.

## Note

"Phase 3" follow-up (not done yet): drop `locations.country` column entirely and make
`locations.city_id` `NOT NULL` once all legacy rows are matched.

## Pre-deploy validation against a real prod snapshot (2026-08-08)

Rehearsed the full migration chain (`d1e4c73f0038` → head) against a restored copy of the actual
production DB (`spacepoint_unified`, 616KB dump, 93 users / 86 `applicant_profiles` / 3 locations /
8 applications). Full schema swept for every `%city%`/`%location%` column, not just the ones this
migration touches.

**Result: clean, with one real bug found and fixed.**

- `applicant_profiles.city_of_residence` — 79/86 populated rows, **100% matched** a seeded city
  case/whitespace-insensitively (includes `"dubai"`, `"Dubai "` with trailing space — both matched
  fine). 7 true NULLs, zero loss.
- `applicant_profiles.deliver_cities` — one real typo, `"Abudhabi"` (no space, 1 row, alongside a
  correct `"Dubai"` in the same array) — **the migration silently drops this** since `trim()` only
  strips leading/trailing whitespace, not internal spaces. Confirmed empirically: ran the migration
  as-is first, watched that applicant's Abu Dhabi tag vanish; applied the one-line fix below, reran
  from a fresh restore, confirmed both cities survive.
- `locations` (3 rows) — `Dubai` and `Abu Dhabi` auto-link correctly. `MZN Hub - Al Ain` does
  **not** (name isn't an exact match for the seeded city "Al Ain") — stays `city_id = NULL`, no
  breakage, just needs a 10-second manual pick in the Catalog UI's Location edit form after deploy.
- `applications.country` / `users.country` — free text, untouched by any migration in this set
  (no destructive change touches them). Not a risk.
- `contacts.city` / `organizations.city` — same `"Abudhabi"` (14 rows) / `"dubai"` typo pattern
  exists here too, but **out of scope**: no migration in this set adds a structured city FK to
  `contacts`/`organizations`, so nothing here is at risk of being dropped. Noted for a future pass
  if that table ever gets the same treatment, not a blocker now.

**Run this on production before applying the migration chain** (idempotent, safe to re-run):

```sql
UPDATE applicant_profiles
SET deliver_cities = array_replace(deliver_cities, 'Abudhabi', 'Abu Dhabi')
WHERE deliver_cities @> ARRAY['Abudhabi'];
```

**Also run before deploying** (already applied on production, 2026-08-08 — noted here for anyone
rehearsing against a fresh snapshot):

```sql
UPDATE users SET country = 'United Arab Emirates' WHERE country = 'UAE';
UPDATE applications SET country = 'United Arab Emirates' WHERE country = 'UAE';
```

## Third act: country free-text → ISO code (2026-08-08)

Closes the two-storage-convention split `CountrySelect.tsx` was built to accommodate (§4 above):
`users.country`, `applicant_profiles.country`, `applications.country` move from free-text display
names onto the same ISO-3166-1 alpha-2 codes `Location.country`/`City.country` already use.
Operator's call, made explicitly after walking through why (locale-dependent display names, country
renames, and it's the same convention already established for `Location`/`City` — see
`backend/app/services/countries.py`'s module docstring for the full reasoning).

- **New:** `backend/app/services/countries.py` — `COUNTRY_NAMES` (code → English name, generated
  once from Node's `Intl.DisplayNames`, the same engine `frontend/src/lib/countries.ts` uses, so
  the two lists can't drift on contested/renamed names) and `resolve_country_code()` (case/
  whitespace-insensitive name-or-code → code, with a `"uae"` alias for the one real-world variant
  seen in production data).
- **Migration** `alembic/versions/cd01bf6967f0_country_codes.py` — per table, per distinct
  non-null value, resolves via `resolve_country_code()` and rewrites in place. No column type
  change. An unresolved value (typo, unrecognized name) is left as-is rather than guessed or
  nulled — same discipline as the `locations` → `city_id` backfill. Verified against both dev and
  a restored prod snapshot: 100% resolved (`AE`/`KW`/`NG`, blanks stay blank) — the pre-deploy
  `UPDATE ... WHERE country = 'UAE'` above means production has zero unresolved values by the time
  this runs.
- **Frontend writers** (`valueType="code"` on `CountrySelect`, was the default `"name"`):
  `Profile.tsx`, `LearnSignup.tsx`, `LearnProfile.tsx`, `ApplyFlow.tsx`, `InstructorApply.tsx`
  (`Catalog.tsx` already used `valueType="code"` — that's `Location`/`City`, unaffected).
- **Frontend readers** — resolve code → name via `getCountries()` at render time (mirrors
  `Catalog.tsx`'s existing `countryName` pattern for `Location`), fixed everywhere a raw
  `.country` was printed: `UserProfileModal.tsx`, `Applications.tsx` (admin), `LearnProfile.tsx`
  (account info), `ApplicantReview.tsx`, ambassador `Leaderboard.tsx` (both the shared table
  component and the standalone teacher table), `AdminAmbassador.tsx`.
- **Backend readers** (human-facing documents, not API JSON — those stay raw codes, frontend's
  job) — `COUNTRY_NAMES.get(code, code)` fixed in: `instructors/admin.py` and
  `instructors/instructor.py` (both build a `living_area` string that gets printed into the
  instructor contract PDF), `admin/users.py` (dossier item `meta` text, rendered directly in
  `UserProfileModal.tsx`), `services/spine/identity.py::find_or_create_contact` (gap-fills
  `Contact.country`, which stays its own independent free-text convention — resolves to a name so
  this doesn't leak a raw code into a field nothing else writes as a code).
- **Found in passing, fixed:** `instructors/admin.py`'s `applicant_detail` endpoint returned the
  raw `ApplicantProfile` ORM object, whose `city_of_residence` column was renamed to
  `city_of_residence_id` earlier in this same cleanup — `ApplicantReview.tsx`'s
  `detail.profile.city_of_residence` reference had gone silently stale (filtered out by
  `.filter(Boolean)`, no crash, just missing from the page). Fixed by resolving the FK server-side
  under the same `city_of_residence` key, matching how `_location_out` already resolves
  `Location.city_id`.
- **Tests:** new `backend/tests/services/test_countries.py` (the resolver, pure function). Updated
  five existing tests that asserted the old display-name convention
  (`test_apply_city.py`, `test_onboard_application.py`, `test_applicant_role_promotion.py`,
  `test_instructor_apply_cities.py`, `test_lms_signup.py`) plus one that asserted
  `find_or_create_contact`'s old pass-through behavior (`test_backfill_user_contacts.py`) to
  match the new, intentional resolve-to-name behavior. Full suite green after.
- **Live-verified:** signup/apply/profile country pickers all submit codes (checked the actual
  `<option value>` in the DOM); a real applicant's already-saved `"AE"` pre-selects correctly on
  profile load; a real `/apply/intern` submission round-tripped through the live API — sent `"AE"`,
  stored `"AE"`, `GET /admin/applications` returned `"AE"` (frontend resolves to the display name
  at render, confirmed via the `Applications.tsx` fix above).
- **Out of scope, left alone:** `Contact.country`/`Organization.country` stay their own
  independent free-text convention — this migration doesn't touch them (only gap-fills into them,
  fixed above); the two ambassador/teacher public-profile endpoints (`ambassadors/public.py`)
  return raw `country` with no frontend consumer found anywhere in this repo — nothing to fix,
  flagged in case an external site consumes that API directly.