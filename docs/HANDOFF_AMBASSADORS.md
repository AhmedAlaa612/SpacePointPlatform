# Ambassadors Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

> Status: verified 2026-09-17 against every router in `routers/ambassadors/` (`leads`, `network`,
> `teacher`, `tasks`, `materials`, `titles`, `badges`, `points`, `achievements`, `dashboard`,
> `public`, `admin`), every model in `models/ambassadors/`, `services/ambassadors/{achievements,
> titles,stats}.py`, `services/points.py`, `app/main.py`'s mount, and the frontend route guards in
> `router.tsx` plus `pages/ambassadors/*`. This pass corrected a wrong lead-type claim, added the
> missing `students_reached` badge criterion, documented the task approval state machine (not
> previously described), and flagged a genuinely misleading column name and a stale code comment as
> gotchas — see below.

Lead-generation and gamified recruiting for ambassadors, who in turn recruit and manage teachers delivering workshops.

## Roles and permissions

- **`admin`** — full control domain-wide: approves/rejects leads, views all leads/activity/leaderboard/points-log, manages titles and badges (CRUD), manages tasks (assign to any ambassador/teacher, approve/reject), can act on any network/session (bypasses ownership checks everywhere), edits `system_settings` (point-reward amounts), approves pending ambassador/teacher signups via `PUT /ambassadors/admin/users/{id}/status`, views deep-dive stats per ambassador/teacher (`GET /ambassadors/admin/users/{id}/ambassador-stats`/`teacher-stats` — note the `/ambassadors/admin/users/...` path is this domain's own router, distinct from the generic `/admin/users/*` account-CRUD router, see Gotchas). Frontend: `/ambassadors/admin/*` pages (Network, Tasks, Leads, Sessions, Titles, Badges, Settings) plus `AdminAmbassador.tsx` (the ambassador/teacher deep-dive page, at `/ambassadors/admin/ambassador/$ambassadorId`).
- **`ambassador`** — creates/edits/withdraws their own leads; sees only their own leads and comments; manages the teachers/instructors they've recruited (`/network/*`) — approves/rejects teacher applications, approves/rejects teacher sessions, marks materials sent; creates and assigns tasks to teachers they invited (and only teachers they invited — `tasks.py:46-48`); adds/edits/deletes materials (any ambassador can edit/delete any material's own upload, or an admin can edit/delete any material — `materials.py:16-26`); sees a dashboard/leaderboard/achievements scoped to the ambassador audience. Frontend: `Dashboard.tsx`, `Leads.tsx`, `Network.tsx`, `network/teacher/$teacherId`, `Tasks.tsx`, `Leaderboard.tsx`, `Materials.tsx`.
- **`teacher`** — creates/edits/cancels their own delivery sessions and marks them done; cannot see or act on leads or network-management endpoints; can browse (but not add) the materials library like any other authenticated user (`materials.py:29-35`, no role check on `GET /materials`); sees a teacher-scoped dashboard/leaderboard instead of the ambassador one. Frontend: `TeacherPortal.tsx`, `TeacherProfile.tsx`; blocked from `/leads` and `/network` by route guards in `router.tsx`.

The core split: ambassadors run the recruiting/lead pipeline and manage a downstream network of teachers; teachers only manage their own delivery sessions and never see leads or other users' data. Both share tasks, materials, leaderboard, and title/badge mechanics, scoped to their own audience. Route guards (`frontend/src/router.tsx`, `ambassadorsLayoutRoute`) admit `ambassador`/`teacher`/`admin` at `/ambassadors/*`, with `/leads` and `/network*` further restricted to `ambassador`/`admin`, and `/admin/*` restricted to `admin`; a `teacher` landing on bare `/ambassadors` is redirected straight to `/ambassadors/teacher-portal`.

## Key flows

### Leads

A `Lead` is a prospective B2B company or B2C individual contact an ambassador submits. `type` is a
free-text string, not a DB enum — the frontend (`Leads.tsx`) only ever sends `"B2B"` or `"B2C"`, and
the backend only special-cases `"B2B"` (company required; `leads.py:41-42`). **The model's own inline
comment is stale** (`models/ambassadors/lead.py:15`: `# 'B2B', 'distributor'`) — nothing in the
running code sends or checks `"distributor"`; treat the comment as aspirational/outdated, not as the
real value set. Created via `POST /leads` (status starts `submitted`), which notifies admins. The
ambassador can edit while still `submitted`, and withdraw while `submitted`/`in review`. Admin moves
it through `submitted` → `in review` → `converted`/`closed` (`PUT /leads/{id}/status`, any of these
four literal strings — no server-side enum validation beyond that fixed set). On the transition to
`converted` (guarded to fire once via a `points_awarded` flag), the owning ambassador is awarded
points (`lead_points_reward`, default 1000, configurable in `system_settings`), and badge/achievement
checks run. Reverting from `converted` (to any other status) reverses the points — deleting a
`points_awarded` lead does too. Comments on a lead are threaded and notify the other party (admin
comments notify the owning ambassador; ambassador comments notify every admin).

### Points/titles/badges

Points are an append-only ledger (`PointsTransaction`, type `earn`/`adjust`) — no balance column; lifetime points are the sum of the ledger (optionally scoped to a season, `stats.py::season_start()` — start of the current UTC calendar month). Points are awarded for: converting a lead (1000 default), recruiting a teacher who becomes active (500 default), completing an approved task (task's own `points_reward`), and delivering a teacher session (200 default, to both the teacher and their referring ambassador). All reward amounts are editable `system_settings` values, read via `services/points.py::get_setting_int`.

**Titles** are an admin-configured rank ladder keyed by `min_points`, per audience (`ambassador` or `teacher`) — current/next title and progress-to-next are computed from lifetime points (`services/ambassadors/titles.py::resolve_title_progress`). **Badges** (`BadgeDefinition` + `Achievement`) are separate, milestone-based unlocks: admin defines a `criteria_type` and a `threshold` per audience; a check runs after any points/status-changing event and grants a badge the first time a threshold is crossed. The full criteria-type list (`services/ambassadors/achievements.py::CRITERIA_TYPES`) is **`converted_leads`, `active_teachers`, `sessions_done`, `students_reached`, `lifetime_points`** for ambassadors — teachers only get the last three (`TEACHER_CRITERIA_TYPES`, since they have no leads/network of their own). `GET /badges/criteria-types` (admin-only) surfaces this split to the admin Badges editor UI.

### Tasks

An `AmbassadorTask` is assignable work with a points reward and an approval workflow — separate from
the Interns-domain `Task` model, despite the shared name (that one lives under `models/interns/`, see
[`HANDOFF_INTERNS.md`](./HANDOFF_INTERNS.md)). Who can assign to whom is enforced in the handler, not
the schema (`tasks.py::create_task`): admin can assign to any active ambassador or teacher; an
ambassador can only assign to a teacher they personally invited (`invited_by_id == current_user.id`).
The status machine (`tasks.py::ASSIGNEE_TRANSITIONS`/`OWNER_TRANSITIONS`) is stricter than a flat
enum:

- The **assignee** can move `pending → accepted`, and `accepted → submitted` or `edit_requested →
  submitted` (attaching `submission` text on the way to `submitted`).
- The **owner** (task creator) or any **admin** can move `submitted → approved`/`rejected`/`edit_requested`.
- **`rejected` is a dead end for the assignee** — there's no transition back to `submitted` from
  `rejected` (only from `accepted` or `edit_requested`), and `PATCH /tasks/{id}` (`TaskUpdate`) can't
  touch `status` at all. The only way out of `rejected` is the owner/admin setting a new status
  directly via `PUT /tasks/{id}/status`, since the owner-side transition table also doesn't offer a
  path out of it — in practice a rejected task effectively needs a brand-new task.
- Points (`task.points_reward`) are awarded exactly once on `→ approved` (guarded by `points_awarded`,
  same pattern as leads/sessions) and reversed if approval is later revoked or the task is deleted.

### Teacher sessions

A `TeacherSession` is a teaching event a teacher schedules (title, date, planned students). Lifecycle: teacher creates it (status `pending`) → their recruiting ambassador (or admin) approves or rejects it → the ambassador marks materials sent (requires `approved`) → the teacher marks it done (requires approved + materials sent + the date has passed), recording attendance and triggering the point awards above. Status also includes `cancelled` (`network.py::cancel_session`, teacher or admin only, blocked once `done`/already `cancelled`). A teacher or admin can edit/cancel/delete a session; a teacher editing an already-approved/rejected session resets it back to `pending` for re-review (with a notification to the recruiting ambassador). Deleting a `done` session reverses the points it had awarded (to both the teacher and, if any, their referring ambassador).

## Gotchas

- **`PointsTransaction.ambassador_id` and `Achievement.ambassador_id` are misleadingly named** — both
  columns hold a `teacher`'s user id too whenever the event is teacher-scoped (e.g.
  `network.py::mark_done` calls `award_points(db, current_user.id, ...)` where `current_user` is the
  *teacher*; `achievements.check_and_grant(db, teacher_id, audience="teacher")` inserts an
  `Achievement` row with `ambassador_id=teacher_id`). There is no separate `teacher_id`/generic
  `user_id` column on either table — don't assume every row in `points_transactions` or `achievements`
  belongs to an ambassador when querying directly.
- **`GET /achievements/me` is hardcoded to the `ambassador` audience** (`routers/ambassadors/
  achievements.py:17`: `ach_service.list_for(db, current_user.id)` — no `audience` param, defaults to
  `"ambassador"`). A teacher calling it gets ambassador-audience badge definitions checked against
  their own id, which is not meaningful. The real teacher-badges surface is the `achievements` field
  already embedded in `GET /teacher/summary`'s response (`routers/ambassadors/teacher.py:53`, which
  correctly passes `audience="teacher"`) — the frontend teacher pages use that, not `/achievements/me`.
- **`routers/ambassadors/admin.py`'s module docstring is stale**: it says generic Users CRUD "already
  lives at `/interns/admin/users`" — that endpoint doesn't exist. Generic user management actually
  lives at `/admin/users/*` (`routers/admin/users.py`, mounted directly under `/admin` in `main.py`,
  nothing to do with `/interns`). This router's own `PUT /admin/users/{id}/status` is a narrower,
  status-only endpoint for activating pending ambassador/teacher signups — not a substitute for full
  user CRUD, and not the same router the docstring points at.
- **`GET /dashboard/stats` and `GET /titles`/`GET /badges` (list) have no role check beyond being
  logged in** (`get_current_active_user`) — a `teacher` can call the ambassador dashboard-stats
  endpoint and will just get mostly-zero/irrelevant numbers back (it unconditionally treats
  `current_user.id` as an ambassador id), rather than a 403. Not a security issue (no cross-user data
  leak), but don't rely on a 403 there for role-gating in tests or new frontend code.
- **`Lead.type` and `TeacherSession.status`/`AmbassadorTask.status` are plain `String` columns, not DB
  enums** — validation (where it exists at all) happens in the router, not the schema or the database.
  A malformed/unexpected value can still be written directly via a script or a future endpoint that
  forgets the check.

## Main DB tables

| Table | What it holds |
|---|---|
| `leads` | B2B/B2C lead submitted by an ambassador; status pipeline |
| `lead_comments` | Threaded comments on a lead |
| `points_transactions` | Append-only points ledger — `ambassador_id` also holds teacher ids for teacher-scoped events (see Gotchas) |
| `titles` | Admin-configured rank ladder, per audience |
| `badge_definitions` | Admin-configured milestone badge (criteria type + threshold), per audience — `criteria_type` ∈ `converted_leads`/`active_teachers`/`sessions_done`/`students_reached`/`lifetime_points` (ambassador), or the last three for teacher |
| `achievements` | Badges actually earned by a user — same `ambassador_id` caveat as `points_transactions` |
| `teacher_sessions` | A teaching session with approval workflow and attendance; `status` ∈ `pending`/`approved`/`done`/`rejected`/`cancelled` |
| `ambassador_tasks` | Assignable task with approval workflow and point reward; `status` ∈ `pending`/`accepted`/`submitted`/`approved`/`rejected`/`edit_requested` |
| `materials` | Shared teaching material library |
| `system_settings` | Generic key/value config (point-reward amounts, etc.) |

## Key files

| Area | Backend | Frontend |
|---|---|---|
| Leads | `routers/ambassadors/leads.py`, models `lead.py`, `lead_comment.py`, `schemas/ambassadors/lead.py` | `pages/ambassadors/Leads.tsx`, `pages/ambassadors/admin/Leads.tsx`, `pages/ambassadors/components/LeadDetailModal.tsx` |
| Points/gamification | `services/points.py`, `services/ambassadors/{titles,achievements,stats}.py`, routers `points.py`, `titles.py`, `badges.py`, `achievements.py`, `dashboard.py`, `public.py`, models `points_transaction.py`, `title.py`, `badge_definition.py`, `achievement.py` | `pages/ambassadors/Dashboard.tsx`, `pages/ambassadors/Leaderboard.tsx`, `pages/ambassadors/admin/{Titles,Badges}.tsx`, `pages/ambassadors/components/{title,Leaderboard,Celebration}.tsx` |
| Tasks | `routers/ambassadors/tasks.py`, model `task.py`, schema `schemas/ambassadors/task.py` | `pages/ambassadors/Tasks.tsx`, `pages/ambassadors/admin/Tasks.tsx`, `pages/ambassadors/components/TaskDetailModal.tsx` |
| Materials | `routers/ambassadors/materials.py`, model `material.py` | `pages/ambassadors/Materials.tsx` |
| Teacher sessions | `routers/ambassadors/network.py` (approve/reject/material-sent/done), `teacher.py` (teacher's own summary + leaderboard), model `teacher_session.py` | `pages/ambassadors/Network.tsx`, `pages/ambassadors/admin/{Sessions,Network}.tsx`, `pages/ambassadors/{TeacherPortal,TeacherProfile}.tsx`, `pages/ambassadors/components/{SessionDetailModal,NetworkTree,FullNetworkTree}.tsx` |
| Admin cross-cutting | `routers/ambassadors/admin.py` (network tree, activity feed, leaderboard, points log, settings, deep-dive stats, account activation), model `system_setting.py` | `pages/ambassadors/admin/Settings.tsx`, `pages/ambassadors/AdminAmbassador.tsx` |
| Public/shareable profile | `routers/ambassadors/public.py` (no auth) | — |
| Routing | — | `router.tsx` (`ambassadorsLayoutRoute`/`ambassadorsRoutes`) |
