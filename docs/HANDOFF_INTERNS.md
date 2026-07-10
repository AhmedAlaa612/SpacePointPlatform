# Interns Domain

Back to [`HANDOFF.md`](./HANDOFF.md).

Project/task tracking for interns organized into teams, with a kanban board driving day-to-day work.

## Roles and permissions

`admin` always passes every check (built into the `RequireRole` guard); the two domain-specific roles below layer on top.

- **`admin`** (`routers/interns/admin.py`, `/interns/admin/*`) — full CRUD on teams (create/update/delete, add/remove members), projects (create/update/delete, assign/unassign teams), epics (create/update/delete for any team), modules, tasks (create/update/delete/assign, across every project), submission review, proposal review, mind-map layout, and can view any user's tracker. Frontend: `Dashboard.tsx`'s admin view (project/epic/task kanban) plus `Admin.tsx` (team CRUD, admin-only route).
- **`leader`** (`routers/interns/leader.py`, `/interns/leader/*`) — scoped to the one team they lead (`Team.leader_id == user.id`). Can view their team and its members, view/update epics belonging to their team, create/update/delete modules within those epics, create/update/delete/assign tasks (verified by walking task → module → epic → team), review submissions and proposals for their team, view team members' trackers. Cannot create teams/projects/epics or assign teams to projects — those are admin-only; a leader only gets an epic once admin has created one for their team.
- **`intern`** (`routers/interns/intern.py`, `/interns/intern/*` — `require_intern` also accepts `leader`) — read-only on projects and epics; sees only tasks assigned to themself; can update status only on their own assigned tasks and submit work; can view (not manage) their own team; can create and view their own proposals.
- **shared** (`routers/interns/shared.py`, no extra role restriction) — self-service profile (`/users/me`), viewing any team's member list.

Frontend role split lives in `Dashboard.tsx`/`KanbanBoard.tsx`: admin gets the full project/epic/task kanban; leader and intern share the `KanbanBoard` component, but leader additionally gets epic drill-down, task creation, proposal review, and module management, while intern only gets "propose idea" / "my proposals" and a submit dialog when dragging a task to done. Route guards live in `frontend/src/router.tsx`: `/interns/*` requires `intern`/`leader`/`admin`; `/interns/admin` requires `admin`.

## Key flows

### Hierarchy: projects → epics → modules → tasks

`Project` → `Epic` (has both `project_id` and `team_id` — an epic is owned by exactly one team) → `Module` (`epic_id`, defaults to a "General" module) → `Task` (`module_id`). Admin creates projects and assigns teams to projects via the `project_teams` join table — a separate concept from epic ownership, since epics are what actually ties a team to a unit of work. Only admin creates epics; leaders create modules and tasks within epics admin has already assigned to their team. `Task.status` and `Epic.status` both use the same `WorkStatus` enum (`todo` / `in_progress` / `done`). Tasks track `expected_time`/`actual_time` (hours), a `due_date`, and assignees via the `task_assignees` join table.

### Board/kanban

`KanbanBoard.tsx` drives drag-and-drop (`@dnd-kit`); the three columns are the three `WorkStatus` values. In leader mode there's an extra drill-down: the default view shows epics as draggable cards (dragging updates `Epic.status`); clicking an epic opens task view for that epic. Admin and intern see tasks directly. Dragging a task to a new column updates its status directly — except when an intern drags a task to "done," which instead opens a submit dialog requiring a link (and optional note + actual time), creating a `TaskSubmission` rather than setting the task done immediately.

### Teams

A `Team` has one `leader_id` and many `members` (via `team_members`, cascades on user removal). Only admin creates teams and manages membership. A leader is resolved by matching `Team.leader_id` to the current user. The team↔project relationship is indirect — a team is linked to a project via `project_teams`, but the operative authorization link for leaders/interns is `Epic.team_id`.

### Submissions/reviews

An intern submits finished work via `POST /intern/tasks/{id}/submit`, creating a `TaskSubmission` (link, optional note, status `submitted`). A leader or admin reviews it (`PATCH .../submissions/{id}/review`), setting a score and comment and flipping status to `reviewed`. Proposals are a separate, lighter-weight idea-submission flow: an intern proposes an idea against an epic; a leader or admin accepts or rejects it, and accepting one pre-fills a task-creation form on the frontend.

## Main DB tables

| Table | What it holds |
|---|---|
| `projects` | Top-level initiative (title, description, status) |
| `project_teams` | Join table — which teams are assigned to a project |
| `teams` | A team, with one `leader_id` |
| `team_members` | Join table — users on a team |
| `epics` | Mid-level grouping under a project, owned by exactly one team |
| `modules` | Grouping of tasks under an epic |
| `tasks` | Unit of work under a module (status, due date, hours) |
| `task_assignees` | Join table — users assigned to a task |
| `task_submissions` | Intern's submitted work for a task (link, note, score, review) |
| `proposals` | Intern-suggested idea tied to an epic (pending/accepted/rejected) |
| `mind_map_layouts` | Per-epic node-position layout (JSON) |
| `task_mind_map_notes` | Per-task free-text note |

## Key files

| Area | Backend | Frontend |
|---|---|---|
| Routers | `routers/interns/{admin,leader,intern,shared}.py` | — |
| Services | `services/interns/{team,project,epic,module,task,proposal,mind_map}.py` | — |
| Models | `models/interns/{project,team,epic,module,task,submission,proposal,mind_map}.py` | — |
| Board/hierarchy | — | `pages/interns/Dashboard.tsx`, `components/kanban/{KanbanBoard,Column,TaskCard,TaskModal,CreateSubtaskModal,EpicDetailModal}.tsx`, `components/ManageModulesModal.tsx` |
| Teams | — | `pages/interns/Admin.tsx` |
| Submissions/proposals | — | `SubmitDialog`, `CreateProposalModal`/`LeaderProposalsModal`/`InternProposalsModal` (inside `KanbanBoard.tsx`), `components/ProposalDetailDialog.tsx` |
| Mind map | — | `pages/interns/MindMap.tsx`, `ProjectMindMap.tsx`, `components/mindmap/SharedNodes.tsx` |
| Tracker | — | `pages/interns/Tracker.tsx` |
| Routing | — | `router.tsx` (role guards) |
