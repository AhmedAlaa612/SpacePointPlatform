# LMS Program & Cohort Analytics — Metrics, Charts & Architecture Spec

> **Purpose of this document**: Self-contained product, data analytics, and engineering specification for upgrading LMS Program & Competition Analytics across **Teams**, **Individuals**, **Missions**, and **Quizzes**. Designed to be handed directly to an implementation agent.

---

## 1. Codebase Context & File Map

| Layer | File Path | Current Role |
| :--- | :--- | :--- |
| **Backend — Team Analytics** | `backend/app/services/competitions/analytics.py` | `cohort_team_analytics()`, `_cohort_roster_user_ids()`, `_individual_done_user_ids()`, `_mission_blocks()`, `_team_mission_runs()` |
| **Backend — LMS Program & Roster** | `backend/app/services/lms/program.py` | `cohort_program_roster()`, `program_roster()`, `assignment_item_detail()`, `_assignment_summary()` |
| **Backend — Cohort Quiz Analysis** | `backend/app/services/lms/cohort_quiz.py` | `get_cohort_quiz_analysis()`, `get_attempt_review()` |
| **Backend — Student Roster Helper** | `backend/app/services/lms/students.py` | `_registered_cohort_users()` (contact_id + email fallback reference) |
| **Frontend — Team Analysis UI** | `frontend/src/pages/admin/components/CompetitionAnalysis.tsx` | `CompetitionAnalysisTab`, `CompletionRateChart`, `DistributionChart`, `ActivityChart`, `TeamTable`, `AttentionList`, `MissionsBlock` |
| **Frontend — Individual Progress UI** | `frontend/src/pages/lms-authoring/components/LmsProgressAndMissions.tsx` | `ProgressPanel`, `ProgressRow`, `AssignmentItemRow`, `QuizAnswersReview`, `ArcadeRunReview` |
| **Frontend — Quiz Analysis UI** | `frontend/src/pages/lms-authoring/components/CohortQuizAnalysisPanel.tsx` | `CohortQuizAnalysisPanel` (Topic mastery, difficulty breakdown, question accuracy) |
| **Frontend — LMS Admin Workspace** | `frontend/src/pages/lms-authoring/LmsProgramAdmin.tsx` & `frontend/src/pages/lms-authoring/components/LmsCohortSection.tsx` | Program/Cohort LMS tabs (`Checklist`, `Missions`, `Components`, `Progress`, `Analysis`) |

---

## 2. Phase 0: Data Integrity & Metric Distortion Fixes (Must Fix First)

### 2.1 Include Team Mission Steps in Team Completion % (`analytics.py`)
- **Bug**: In `cohort_team_analytics()` (`analytics.py` ~L382), `team_items` excludes `i.item_type == "mission_run"`. Teams with 1/1 `team_setup` done and 0/6 Madar CubeSat design steps done report **100% completion**.
- **Fix**:
  - Include team-scoped `mission_run` checklist items in the team denominator, **or** compute a `composite_pct` alongside `deliverables_pct`:
    `Team Composite % = (Completed Team Deliverables + Confirmed Mission Steps + Avg Member Individual Items Done) / (Total Team Deliverables + Total Mission Steps + Total Individual Items)`
  - When a checklist item has `item_type == "mission_run"` and `mission_step_key` set, evaluate its completion per team/student by checking if `mission_step_key in Design.confirmed_steps` (for Madar design missions) or `MissionAttempt.status == "passed"`.

### 2.2 Fix `_cohort_roster_user_ids()` Missing Email Fallback & Mode Partitioning (`analytics.py`)
- **Bug**: `_cohort_roster_user_ids(db, cohort_id)` (~L108) only resolves `Registration.contact_id == User.contact_id` and ignores `mode: Literal["participant", "observer", "all"]`. This causes `totals.registered_students` and `totals.students_without_team` to undercount email-matched accounts and leak observer registrations into participant KPIs.
- **Fix**:
  - Refactor `_cohort_roster_user_ids(db, cohort_id, mode="participant")` to use the same 2-step resolution as `_registered_cohort_users()` in `services/lms/students.py` (`User.contact_id` first, then `func.lower(User.email) == func.lower(Contact.email)` fallback).
  - Filter out observer assignments (`LmsProgramAssignment.mode == "observer"`) when `mode == "participant"`, and filter to observers only when `mode == "observer"`.

### 2.3 Reconcile `arcade_game` & `mission_run` in `_individual_done_user_ids()` (`analytics.py`)
- **Bug**: `_individual_done_user_ids()` (~L175) batch-reconciles `course` and `quiz` items against live completions, but does not reconcile `arcade_game` (`ArcadeGameAttempt.passed == True`) or individual `mission_run` (`mission_step_key in Design.confirmed_steps`).
- **Fix**: Add batch reconciliation for `arcade_game` and `mission_run` items so individual progress inside Team Analytics never lags behind actual game/mission state.

### 2.4 Eliminate N+1 Query Cascade in `cohort_program_roster()` and `program_roster()` (`program.py`)
- **Bug**: `cohort_program_roster()` (~L2382) and `program_roster()` (~L2442) loop `for assignment in assignments:` and run `db.get(User)`, `_assignment_summary()`, `_assignment_items_and_progress()`, and `_team_progress_by_item()` per student (`4 * N` queries).
- **Fix**: Batch-preload all `User` rows, `LmsProgramItemProgress` rows, `LmsProgramTeamItemProgress` rows, and `TeamMember`/`Team` mappings for the cohort/program in 4 set-based queries and assemble summaries in memory.

---

## 3. Core Metrics & Charts Specification

### 3.1 Executive KPI Strip (Cohort & Individual Progress Header)
Render at the top of both the Unified Cohort Analysis view and the Individual `ProgressPanel`:

| KPI Card | Primary Value | Secondary / Subtitle Signal | Formula / Source |
| :--- | :--- | :--- | :--- |
| **1. Activated Roster** | `activated_count / total_assigned` (`%`) | `N never logged in` · `M without team` | `User.last_login_at IS NOT NULL` or `>= 1` item started |
| **2. Overall Progress** | `mean_completion_pct` (`%`) | `Median: X%` · `Certified: Y%` | Mean & median of student/team completion `%` across assigned checklist |
| **3. Team Health** *(if teams)* | `balanced_teams / total_teams` | `X Solo-Carried` · `Y Stalled >7d` | See §3.4 Free-Rider / Collaboration Index |
| **4. Awaiting Confirmation** | `awaiting_confirmation_count` | `Oldest waiting: Xh` (Clickable filter) | Items with `requires_confirmation == True` and `status == "completed"` |
| **5. Deadline / SLA Risk** | `at_risk_count` or `overdue_count` | `Next deadline in Xh: <Item Title>` | Incomplete items where `deadline_at < now` (overdue) or `deadline_at < now + 48h` |
| **6. Quiz Mastery** *(if quiz)* | `avg_quiz_score_pct` (`%`) | `Submitted: X/Y (Z%)` · `Weakest: <Topic>` | Mean score across `CohortQuizAttempt.status == "submitted"` |

---

### 3.2 Chart 1: Sequential Roadmap Funnel & Bottleneck Detector
- **Goal**: Identify which exact checklist item in a sequential or multi-step program is blocking students/teams from progressing.
- **Data Model (Per `LmsProgramItem` ordered by `position`)**:
  - `item_id`, `position`, `title`, `item_type`, `scope` (`individual` | `team`), `deadline_at`
  - `unlocked_count`: Students/teams for whom predecessor items are complete (or total assigned if `sequential_unlock == False`).
  - `done_count`: Confirmed/completed count (`pct_done`).
  - `awaiting_confirmation_count`: Submitted, waiting on admin sign-off (`pct_awaiting`).
  - `in_progress_count`: Started (`Course` > 0%, `Quiz` `in_progress`, `Arcade` >= 1 failed attempt, `Mission` started) (`pct_in_progress`).
  - `step_dropoff_pct`: `((Completed_{i-1} - Completed_i) / Completed_{i-1}) * 100`
  - `effort_metric`:
    - For `arcade_game`: `avg_attempts_to_pass` (`count(ArcadeGameAttempt) / count(distinct passed user_id)`).
    - For `quiz`: `avg_score_pct` and `timeout_rate_pct`.
    - For `course`: `median_completion_minutes`.
- **Visual Encoding**:
  - Horizontal 3-segment stacked progress bar per item (`Done` emerald `#047857` / `#199e70`, `Awaiting Confirmation` amber `#d97706` / `#c98500`, `In Progress` sky blue, remainder neutral track).
  - **Bottleneck Callout Badge**: Automatically highlight the item with the highest `step_dropoff_pct` (>= 20%) in an amber callout border showing its effort metric (e.g., `⚠️ Bottleneck: -26% drop-off · Avg 9.4 arcade runs per pass`).
  - **Deadline Badge**: Show `Overdue` (red) or `Due in Xh` (amber) when `deadline_at` is set.

---

### 3.3 Chart 2: Multi-Signal Daily Activity Velocity Timeline
- **Problem Solved**: Current `ActivityChart` in `CompetitionAnalysis.tsx` only groups `LmsProgramTeamItemProgress.updated_at` by day, which overwrites historical activity whenever a team updates a link and ignores 80% of learner events.
- **Data Model (`activity_series: list[DailyActivityBucket]`)**:
  Union immutable event timestamps grouped by calendar date (`YYYY-MM-DD`, UTC+3):
  1. `course_completions`: `LmsProgramItemProgress.completed_at` where `item_type in ("course", "article", "custom")`
  2. `quiz_submissions`: `CohortQuizAttempt.submitted_at`
  3. `arcade_runs`: `ArcadeGameAttempt.created_at`
  4. `mission_confirmations`: `Design.updated_at` / `MissionAttempt.updated_at`
  5. `team_deliverables`: `LmsProgramTeamItemProgress.completed_at` (fallback `updated_at`)
- **Visual Encoding**:
  - Daily stacked vertical bar chart (last 14 or 30 days, or cohort `starts_on` -> `ends_on`) color-coded by activity signal, with vertical dashed reference lines for item `deadline_at` dates.

---

### 3.4 Chart 3: Team Collaboration Health & "Free-Rider / Solo-Carried" Detection
- **Goal**: Catch teams that look healthy on the surface (e.g., 80% team links submitted) because 1 student is doing all the work while teammates have 0% individual progress or never logged in.
- **Metrics per Team (`TeamAnalyticsRow`)**:
  - `member_count`: Total members on team.
  - `active_member_count`: Members with `last_login_at IS NOT NULL` AND `individual_pct > 0`.
  - `distinct_submitter_count`: `len(set(row.updated_by_user_id for row in team_progress_rows if row.updated_by_user_id))`
  - `member_pct_spread`: `max(m.individual_pct) - min(m.individual_pct)`
  - `collaboration_status`:
    - `"solo_carried"` (🔴 Red): `team_deliverables_pct >= 50` AND (`distinct_submitter_count == 1` with `member_count >= 2`) AND (`min(m.individual_pct) < 20` or >= 1 member never logged in).
    - `"imbalanced"` (🟡 Amber): `member_pct_spread >= 50` or >= 1 member inactive > 7 days.
    - `"stalled"` (🟠 Amber): All members inactive > 7 days and `composite_pct < 100`.
    - `"balanced"` (🟢 Emerald): All members active with `member_pct_spread < 50`.
- **Visual Encoding**:
  - Add a **Collaboration Health Badge** (`🔴 Solo-Carried (1/3 active)`, `🟢 Balanced (3/3 active)`) on `TeamTable` rows.
  - Add a **"Solo-Carried / Imbalanced Teams"** group in `AttentionList` (Actionable Triage).
  - Inside the expanded `TeamTable` row (`MemberProgressDetail`), show per-member attribution: `"Submitted K of M team deliverables · Last login: Xd ago · Course: A% · Quiz: B%"`.

---

### 3.5 Chart 4: Madar CubeSat 9-Phase Engineering Funnel (`MissionsBlock` Upgrade)
- **Problem Solved**: `_mission_blocks()` in `analytics.py` (~L220) only inspects `MissionAttempt.status` (`passed` | `in_progress` | `not_started`), collapsing all 9 steps of a Madar CubeSat design mission into a single `"in_progress"` bar.
- **Data Model**:
  - For any mission with sequential steps (`MADAR_STEPS = ["setup", "mission_def", "conops", "components", "power_budget", "simulation", "TradeStudy", "failure_modes", "cdr"]`), aggregate `Design.confirmed_steps` across all cohort teams/individuals:
  - Return `step_funnel: list[{ step_key, label, confirmed_count, pct, dropoff_from_prev_pct }]`.
- **Visual Encoding**:
  - Render a **9-Stage Phase Stepper / Funnel Grid** inside `MissionsBlock` showing `confirmed_count / total_teams` and `%` per engineering phase, highlighting the phase with the largest drop-off (e.g., `Phase 5: Power Budget — 53% (-33% drop)`).

---

### 3.6 Chart 5: Upgraded Cohort Quiz Psychometrics (`cohort_quiz.py` & `CohortQuizAnalysisPanel.tsx`)

#### A. Quiz Completion Funnel & Score Distribution Histogram
- Extend `CohortQuizAnalysisOut` in `backend/app/services/lms/cohort_quiz.py`:
  - `assigned_count`: Total students assigned the quiz checklist item.
  - `submitted_count`: `status == "submitted"`.
  - `in_progress_count`: `status == "in_progress"` (flags students who abandoned mid-quiz or had browser/timer issues).
  - `not_started_count`: `assigned_count - submitted_count - in_progress_count`.
  - `score_buckets`: Counts of submitted attempts in `0–49%`, `50–69%`, `70–89%`, `90–100%`.

#### B. Per-Question Timeout Separation & Timing Telemetry
- Currently `CohortQuizAnswer` records `timed_out: bool` and `time_taken_seconds: int`, but `get_cohort_quiz_analysis()` ignores them.
- Extend `QuestionStat` with:
  - `timeout_count`: Count of answers where `timed_out == True`.
  - `wrong_selected_count`: Count of graded wrong answers where `timed_out == False` and `is_correct == False`.
  - `avg_time_seconds`: Mean `time_taken_seconds` across attempts.
  - `time_limit_seconds`: Configured question timer limit.
- **Visual Encoding**:
  - Replace the 2-part bar (`Right` / `Wrong`) with a **3-part stacked bar**:
    1. 🟢 **Correct** (`correct_count`)
    2. 🔴 **Wrong Option Chosen** (`wrong_selected_count`)
    3. ⏱️ **Timed Out** (`timeout_count`) + badge `⏱️ X% Timed Out (Avg Ys / Zs limit)` when `timeout_rate >= 15%`.

#### C. Distractor Analysis (Option Selection Distribution)
- Extend `QuestionStat` with `option_stats: list[OptionStat]`:
  - `option_id: str`, `text: str`, `is_correct: bool`, `selected_count: int`, `selected_pct: float`.
- **Visual Encoding**:
  - Clicking any MCQ row in `CohortQuizAnalysisPanel.tsx` expands a **Distractor Breakdown Drawer** showing horizontal bars for Option A / B / C / D.
  - Automatically badge any wrong option chosen by >= 25% of students as `⚠️ Top Misconception`.

#### D. Aggregate Open-Ended (`textarea`) & Poll Response Viewer
- Currently, ungraded / `textarea` questions only render `"Opinion / Open-ended · N total responses · Ungraded"` with no way to read the responses.
- Extend `QuestionStat` with `text_responses: list[{ user_id, student_name, team_name, text_response, submitted_at }]` (for `question_type == "textarea"`).
- **Visual Encoding**:
  - Clicking an open-ended question row expands a scrollable, searchable feed of student text responses directly inside `CohortQuizAnalysisPanel.tsx`.

---

### 3.7 Individual `ProgressPanel` Enhancements (`LmsProgressAndMissions.tsx`)
1. **Quick-Filter Pill Bar**:
   - `All (N)` | `⏳ Needs Confirmation (K)` | `🔴 Stalled / 0% (M)` | `⚡ Speed-Runners (S)` | `🎓 Certified (C)`
2. **Speed-Runner / Low-Dwell Anomaly Flag**:
   - Flag students who complete a multi-lesson `course` in `< 120` seconds (`completed_at - created_at < 120s`) and subsequently fail the quiz (`< 50%`), surfacing superficial click-through behavior.
3. **Team Badge & Last Active Timestamp on Every Student Row**:
   - Display the student's `team_name` badge and `last_activity_at` relative time (`"2h ago"`, `"8d inactive"`, `"Never logged in"`) directly on `ProgressRow`.
4. **Batch Confirmation & XLSX Export**:
   - Add `"Confirm All Eligible (K)"` batch action and `"Export Progress XLSX"` button (exporting Student, Email, Team, Status, Completion %, Quiz Score %, Madar Step, Last Login).

---

### 3.8 Program-Scope Cross-Cohort Benchmark View (`LmsProgramAdmin.tsx`)
- **Problem Solved**: Selecting `"Program"` scope on `/lms-authoring/curriculum` and clicking `"Analysis"` (`LmsProgramAdmin.tsx` ~L322) currently renders an empty state: *"Pick a cohort to view quiz analysis"*.
- **Replacement**:
  - Create endpoint `GET /lms/programs/{program_id}/analytics-benchmark` returning per-cohort summary rows for all cohorts linked to that `LmsProgram`:
    - `cohort_id`, `cohort_name`, `status`, `enrolled_count`, `activation_pct`, `avg_completion_pct`, `certified_pct`, `avg_quiz_mastery_pct`, `mission_pass_pct`, `top_bottleneck_item_title`.
  - Render a **Cross-Cohort Comparison Matrix Table** so admins can benchmark cohorts side-by-side and click any row to drill into that cohort's analysis.

---

## 4. Recommended Implementation Order for Agent

1. **Step 1 (Backend Accuracy & Performance)**:
   - Fix `_cohort_roster_user_ids` (email fallback + `mode` filter) and `_individual_done_user_ids` (`arcade_game` + `mission_run` reconciliation) in `backend/app/services/competitions/analytics.py`.
   - Batch-optimize `cohort_program_roster` and `program_roster` in `backend/app/services/lms/program.py`.
2. **Step 2 (Backend Telemetry Enrichment)**:
   - Add `step_funnel` (9-phase `Design.confirmed_steps`), `collaboration_status` (Free-Rider index), `step_dropoff_pct`, and multi-signal `activity` series to `cohort_team_analytics()` in `analytics.py`.
   - Add `option_stats` (distractors), `timeout_count`, `avg_time_seconds`, `score_buckets`, `in_progress_count`, and `text_responses` to `get_cohort_quiz_analysis()` in `backend/app/services/lms/cohort_quiz.py`.
3. **Step 3 (Frontend Charts & Triage Upgrades)**:
   - Upgrade `CompetitionAnalysis.tsx` (`MissionsBlock` 9-step funnel, `TeamTable` collaboration health badges, `CompletionRateChart` bottleneck & deadline badges, multi-signal `ActivityChart`).
   - Upgrade `CohortQuizAnalysisPanel.tsx` (3-part Correct/Wrong/Timeout bars, expandable Distractor drawer, expandable Open-Ended response feed, Quiz funnel & score histogram).
   - Upgrade `ProgressPanel` in `LmsProgressAndMissions.tsx` (KPI strip, status filter pills, team badges, XLSX export) and `LmsProgramAdmin.tsx` (Program-scope Cross-Cohort Benchmark table).
