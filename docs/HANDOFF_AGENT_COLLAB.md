# Working With This Operator — Agent-to-Agent Handoff

Written 2026-08-20 by the agent that ran the LMS Stripe/Poster work directly with the operator
(Ahmed), for any other cloud agent now picking up a *different* branch of the August Build Brief
(Competition, Ops-flow, backlog items) concurrently. Not architecture — that's `HANDOFF.md` and
its domain docs. This is process: how this specific operator works, and two mistakes worth not
repeating.

---

## 1. Scope split — don't collide

This session owns the **LMS/Missions/Games domain** (`HANDOFF_LMS.md`) — `backend/app/{models,
routers,services}/{lms,missions,games}/`, `frontend/src/pages/{learn,lms-authoring}/**`. Stay out
of that surface unless the operator explicitly asks you to touch it; ask him first if a task
looks like it needs to.

**Already shipped from this side** (all merged to `main`): Poster/Canva template link fields on
the Design mission (PR #2), Stripe Checkout for paid LMS courses — `Purchase` model, webhook,
checkout flow (PR #3), course create/edit access+price UI (PR #4).

**Known adjacent-domain dependency, already satisfied**: Team generalization — `MissionTeam`
lifted into a top-level `Team`/`TeamMember` (tables `learner_teams`/`learner_team_members`,
migration `a1f0c9b2d4e7`) — landed on `main` before any of the above, authored by a different
session. Documented in `HANDOFF_LMS.md` §4. If you're picking up the **Competition domain**
(August Build Brief Branch 2), this is the prerequisite the brief calls "the single biggest
architectural move" — it's done, build on it, don't redo it.

---

## 2. Git discipline — the one mistake worth not repeating

This repo has multiple agents *and* the operator merging to `main` directly, sometimes several
times a day. A branch you created even a few hours ago can already be stale.

**I got this wrong once this session**: branched without fetching first, built a whole feature,
and only found out afterward — because the operator asked, not because I checked — that two
other migrations had landed on `main` with the same `down_revision` as mine (a real single-
Alembic-head violation, `HANDOFF.md` §9). Recoverable (merged main in, rebased the migration's
`down_revision` onto the new head), but avoidable.

- **Every work session, before branching**: `git fetch origin main && git checkout -B
  <your-branch> origin/main`. Don't reuse an old local branch without doing this first, even mid-
  session.
- **Right before opening a PR**: `git fetch origin main` again, confirm `git log --oneline
  HEAD..origin/main` is empty. If it's not, merge main in and resolve before pushing — don't push
  and let CI or the operator find the conflict.
- **Always run `alembic heads` fresh** before writing a new migration's `down_revision` — never
  trust what a plan doc or a stale mental model says the head is. Verify with the throwaway-
  autogenerate-diff trick (`HANDOFF.md` §9) that your migration matches the models exactly before
  committing it.
- If a PR you opened already merged and you're doing follow-up work, **restart your branch from
  `origin/main`** rather than stacking new commits on old, already-merged history.

---

## 3. Verification discipline — plans go stale fast

The operator sometimes hands you a plan file another agent (or a prior session) wrote. Treat it
as a strong starting point, not ground truth — this codebase moves fast enough that file paths,
line numbers, and even which schema file something lives in can be wrong by the time you actually
implement. I found two real inaccuracies in a plan during the Stripe build (a frontend reference
pointing at the wrong page — a mission editor, not the course editor — and a schema file that had
moved) purely by grepping the actual current code before trusting the plan's citations. Do that
first; fix silently if it's a path/line-number slip, flag it to the operator if it changes scope.

Before calling anything done:
- Migrate a **real** local Postgres dev + test DB through the full chain, not just check the
  migration applies in isolation.
- Run the **full** backend test suite, not just your new tests — compare the failure count and
  names against the baseline *before* your change. Zero new regressions is the bar. (Baseline as
  of this session: 4 pre-existing failures, all environment-only — LibreOffice isn't installed in
  this sandbox — never assume a new failure is "probably the same thing" without checking.)
- `npm run build` with `VITE_API_URL` set, matching the real CI command — **not** `tsc --noEmit`,
  which is a documented no-op against this repo's root `tsconfig.json` (`HANDOFF.md` §8.20).
- Do a live smoke test against a real local Postgres/Redis when you can reach one. **This
  sandbox's outbound network cannot reach third-party APIs** (confirmed against `api.stripe.com`
  specifically) — if a feature genuinely needs to prove a live external call, say so plainly
  rather than claiming full verification. The operator will do that leg locally or on the VPS;
  your job is to get everything else airtight first so that's the only unknown left.

---

## 4. Working with this operator specifically

- **Direct, low-fluff answers.** He tests everything for real — his own Stripe keys, a real VPS,
  actual error text pasted or screenshotted — and will immediately notice if an answer doesn't
  match what he's actually seeing. Verify against the real code before answering; don't guess
  from memory or from what a doc *says* should be true.
- **He's on Windows, using conda, in PowerShell.** Bash syntax (`&&`, `source ...`) doesn't
  translate — give PowerShell-correct commands whenever the answer touches his machine, and expect
  Windows-specific friction (port exclusion ranges, execution policy, PATH issues after an
  install) that has nothing to do with your code.
- **He will occasionally screenshot something with real secrets in it.** Happened once already —
  a live Stripe key plus SMTP/admin passwords, fully readable in a photographed `.env`. If that
  happens: don't echo the values back into the conversation, say so plainly, and recommend
  rotating the exposed credential. Don't just quietly note it and move on.
- **Confirm before anything touching the live VPS, a shared branch, or real money** (a live Stripe
  charge, a production deploy). This environment has no VPS/production access anyway — your job
  is to prepare the code and tell him exactly what to run, not to run it yourself. He drives those
  steps in his own terminal.
- **When a plan or a prior assumption turns out wrong, say so plainly** and explain what the code
  actually does. He wants the real answer, not a hedge — and he'll ask a direct follow-up if
  something doesn't add up, so don't paper over a gap hoping it won't come up.
- **Ask him directly when genuinely blocked or when a decision is his to make** (which of two
  designs, whether to spend real money on a test, whether to touch a domain outside your scope) —
  he answers fast and directly, matching how he expects you to communicate back.

---

## 5. Where things stand as of this handoff (2026-08-20)

Per the August Build Brief's priority order:
- ✅ Team generalization (prerequisite for Competition) — merged.
- ✅ Poster/Canva (Branch 3) — merged.
- ✅ Stripe Checkout for LMS courses (Branch 4) — merged, live-tested by the operator against
  real Stripe test-mode keys (full purchase → refund → repurchase cycle confirmed working), VPS
  deploy in progress at time of writing.
- ⬜ **Competition domain (Branch 2)** — not started. Real external deadline: Aug 31. Highest
  priority of what's left.
- ⬜ Ops-flow overhaul (Branch 1) — not started.
- ⬜ Backlog triage items — untouched.

The operator has UX feedback pending on the LMS/courses portal surface — expect follow-up work
in that scope from this session, not from whoever picks up Competition/Ops-flow.
