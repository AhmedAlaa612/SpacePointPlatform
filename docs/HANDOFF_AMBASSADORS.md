# Ambassadors Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

Lead-generation and gamified recruiting for ambassadors, who in turn recruit and manage teachers delivering workshops.

## Roles and permissions

- **`admin`** — full control domain-wide: approves/rejects leads, views all leads/activity/leaderboard/points-log, manages titles and badges (CRUD), manages tasks (assign to any ambassador/teacher, approve/reject), can act on any network/session (bypasses ownership checks everywhere), edits `system_settings` (point-reward amounts), approves pending ambassador/teacher signups, views deep-dive stats per ambassador/teacher. Frontend: `/ambassadors/admin/*` pages (Network, Tasks, Leads, Sessions, Titles, Badges, Settings) plus `AdminAmbassador.tsx`.
- **`ambassador`** — creates/edits/withdraws their own leads; sees only their own leads and comments; manages the teachers/instructors they've recruited (`/network/*`) — approves/rejects teacher applications, approves/rejects teacher sessions, marks materials sent; creates tasks for teachers they invited; browses/adds materials; sees a dashboard/leaderboard/achievements scoped to the ambassador audience. Frontend: `Dashboard.tsx`, `Leads.tsx`, `Network.tsx`, `network/teacher/$teacherId`, `Tasks.tsx`, `Leaderboard.tsx`, `Materials.tsx`.
- **`teacher`** — creates/edits/cancels their own delivery sessions and marks them done; cannot see or act on leads or network-management endpoints; sees a teacher-scoped dashboard/leaderboard instead of the ambassador one. Frontend: `TeacherPortal.tsx`, `TeacherProfile.tsx`; blocked from `/leads` and `/network` by route guards.

The core split: ambassadors run the recruiting/lead pipeline and manage a downstream network of teachers; teachers only manage their own delivery sessions and never see leads or other users' data. Both share tasks, materials, leaderboard, and title/badge mechanics, scoped to their own audience.

## Key flows

### Leads

A `Lead` is a prospective B2B company or B2C individual contact an ambassador submits (`type`: `B2B` / `distributor`; company required for B2B). Created via `POST /leads` (status starts `submitted`), which notifies admins. The ambassador can edit while still `submitted`, and withdraw while `submitted`/`in review`. Admin moves it through `submitted` → `in review` → `converted`/`closed`. On the transition to `converted` (guarded to fire once via a `points_awarded` flag), the owning ambassador is awarded points (`lead_points_reward`, default 1000, configurable in `system_settings`), and badge/achievement checks run. Reverting from `converted` reverses the points. Comments on a lead are threaded and notify the other party.

### Points/titles/badges

Points are an append-only ledger (`PointsTransaction`, type `earn`/`adjust`) — no balance column; lifetime points are the sum of the ledger (optionally scoped to a season). Points are awarded for: converting a lead (1000 default), recruiting a teacher who becomes active (500 default), completing an approved task (task's own `points_reward`), and delivering a teacher session (200 default, to both the teacher and their referring ambassador). All reward amounts are editable `system_settings` values.

**Titles** are an admin-configured rank ladder keyed by `min_points`, per audience (ambassador or teacher) — current/next title and progress-to-next are computed from lifetime points. **Badges** (`BadgeDefinition` + `Achievement`) are separate, milestone-based unlocks: admin defines a `criteria_type` (e.g. converted leads, active teachers, sessions delivered, lifetime points) and a threshold; a check runs after any points/status-changing event and grants a badge the first time a threshold is crossed.

### Teacher sessions

A `TeacherSession` is a teaching event a teacher schedules (title, date, planned students). Lifecycle: teacher creates it (status `pending`) → their recruiting ambassador (or admin) approves or rejects it → the ambassador marks materials sent (requires `approved`) → the teacher marks it done (requires approved + materials sent + the date has passed), recording attendance and triggering the point awards above. A teacher or admin can edit/cancel/delete a session; a teacher editing an already-approved/rejected session resets it back to `pending` for re-review. Deleting a `done` session reverses the points it had awarded.

## Main DB tables

| Table | What it holds |
|---|---|
| `leads` | B2B/B2C lead submitted by an ambassador; status pipeline |
| `lead_comments` | Threaded comments on a lead |
| `points_transactions` | Append-only points ledger |
| `titles` | Admin-configured rank ladder, per audience |
| `badge_definitions` | Admin-configured milestone badge (criteria + threshold), per audience |
| `achievements` | Badges actually earned by a user |
| `teacher_sessions` | A teaching session with approval workflow and attendance |
| `ambassador_tasks` | Assignable task with approval workflow and point reward |
| `materials` | Shared teaching material library |
| `system_settings` | Generic key/value config (point-reward amounts, etc.) |

## Key files

| Area | Backend | Frontend |
|---|---|---|
| Leads | `routers/ambassadors/leads.py`, models `lead.py`, `lead_comment.py`, `schemas/ambassadors/lead.py` | `Leads.tsx`, `admin/Leads.tsx`, `components/LeadDetailModal.tsx` |
| Points/gamification | `services/points.py`, `services/ambassadors/{titles,achievements,stats}.py`, routers `points.py`, `titles.py`, `badges.py`, `achievements.py`, `dashboard.py`, `public.py`, models `points_transaction.py`, `title.py`, `badge_definition.py`, `achievement.py` | `Dashboard.tsx`, `Leaderboard.tsx`, `admin/Titles.tsx`, `admin/Badges.tsx`, `components/title.tsx`, `components/Leaderboard.tsx`, `components/Celebration.tsx` |
| Teacher sessions | `routers/ambassadors/network.py` (approve/reject/material-sent/done), `teacher.py` (teacher's own summary), model `teacher_session.py` | `Network.tsx`, `admin/Sessions.tsx`, `admin/Network.tsx`, `TeacherPortal.tsx`, `TeacherProfile.tsx`, `components/SessionDetailModal.tsx`, `components/{NetworkTree,FullNetworkTree}.tsx` |
| Tasks & materials | `routers/ambassadors/tasks.py`, `materials.py`, models `task.py`, `material.py` | `Tasks.tsx`, `admin/Tasks.tsx`, `components/TaskDetailModal.tsx`, `Materials.tsx` |
| Admin cross-cutting | `routers/ambassadors/admin.py` (network tree, activity feed, leaderboard, points log, settings, deep-dive stats), model `system_setting.py` | — |
