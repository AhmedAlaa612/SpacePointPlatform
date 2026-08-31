"""Builds "Competitions — Operations Guide" (.docx, on the SPACE. letterhead)."""

from pathlib import Path

from guide_kit import Guide

OUT = Path(__file__).parent / "Competitions - Operations Guide.docx"


def build() -> Path:
    g = Guide(
        "Competitions — Operations Guide",
        "Setting up, running, judging and closing a competition on the SpacePoint platform",
        [
            ("Audience", "Operations and admin staff running a competition end to end"),
            ("You need", "An account with the **operations** or **admin** role (facilitators can author checklists but not run judging)"),
            ("Covers", "Program setup → phase cohorts → checklists → roster import → rubric → judges → progress tracking → publishing → advancing teams"),
            ("Version", "1.0  ·  31 August 2026"),
            ("Owner", "SpacePoint Operations"),
        ],
    )

    # ── 1. How it fits together ──────────────────────────────────────
    g.h1("1. How a competition is put together", page_break=False)
    g.para(
        "A competition is not a separate system with its own menu. It is the ordinary "
        "**Program → Cohort → LMS checklist** machinery you already use for workshops, with three "
        "things added on top: a program **type** of Competition, checklist steps that can be "
        "**shared by a whole team** instead of per student, and a **judging** area on each cohort."
    )
    g.para(
        "Everything else — courses, missions, certificates, the student's Learn area — behaves exactly "
        "as it does for any other program. If you can run a workshop cohort, you already know most of this."
    )

    g.h2("The words used in this guide")
    g.table(
        ["Term", "What it means here"],
        [
            ["Program", "The competition itself, e.g. *Ru'ya Space Race: SatKit Edition*. Created once, with **Type = Competition**."],
            ["Cohort", "**One phase of the competition** — Qualifiers, Semi-finals, Finals. One cohort per phase, all under the same program."],
            ["LMS program / checklist", "The list of steps students work through. Created once against the program, then tailored per cohort."],
            ["Team", "2–3 students inside one cohort. A team belongs to exactly one cohort — advancing to the next phase creates a new same-named team there."],
            ["Team step", "A checklist step where the whole team shares one submission (poster, video, CAD, dashboard link…)."],
            ["Rubric", "The scoring criteria. Set once on the **program**, so every phase is scored on the same criteria."],
            ["Judge", "A cohort-scoped account that can only see the teams of the phase they were added to, and only their own scores."],
            ["Publish", "Closing scoring on a phase. Judges can no longer change anything until you unpublish."],
            ["Advance", "Moving selected teams from one phase's cohort into the next one. Always a deliberate action — nothing is automatic."],
        ],
        widths=[1.45, 5.05],
    )

    g.h2("The order of work")
    g.table(
        ["#", "Step", "Where"],
        [
            ["1", "Create the program, Type = Competition", "Operations → Programs"],
            ["2", "Create one cohort per phase", "Operations → Cohorts"],
            ["3", "Create the LMS program (checklist)", "LMS Programs"],
            ["4", "Build each **cohort's** checklist", "LMS Programs → cohort tab"],
            ["5", "Import the team roster", "Cohort → Judging → Roster"],
            ["6", "Fix any roster gaps by hand", "Cohort → Judging → Teams"],
            ["7", "Write the rubric", "Cohort → Judging → Rubric"],
            ["8", "Invite the judges", "Cohort → Judging → Judges"],
            ["9", "Track progress (checklists, missions, scoring)", "LMS Programs → Progress  ·  Judging → Judges"],
            ["10", "Publish the results", "Cohort → Judging → Results"],
            ["11", "Advance the teams that go through", "Cohort → Judging → Results"],
            ["12", "Repeat 4–11 for the next phase", "—"],
        ],
        widths=[0.5, 3.2, 2.8],
    )

    g.callout(
        "Rule",
        "Steps 5–11 all live on **one cohort**. If you are ever unsure which phase you are editing, "
        "check the page title — the Judging page always reads *Judging — <cohort name>*.",
    )

    # ── 2. Program ───────────────────────────────────────────────────
    g.h1("2. Create the program")
    g.para("The program is the competition as a whole. You create it once, no matter how many phases it has.")
    g.steps([
        "Go to **Operations → Programs** (`/operations/programs`).",
        "Click **New program**.",
        "Fill in **Code** (e.g. `RUYA-SATKIT-2026`) and **Name** (e.g. *Ru'ya Space Race: SatKit Edition*).",
        "Set **Type** to **Competition**. This is the only thing that makes it a competition — there is no separate switch.",
        "Set **Pricing model** (competitions are normally *Free*), and leave **Default capacity** empty or set the expected number of students.",
        "**Completion requirement** and **Description** work as they do for any program; the description is shown to students.",
        "Click **Create program**.",
    ])
    g.screenshot(
        "The New program dialog with Type set to Competition",
        where="Operations → Programs → New program",
        annotate=[
            "Circle the **Type** dropdown showing *Competition*.",
            "Point at **Code** and **Name** with the real values you used.",
        ],
    )
    g.callout(
        "Note",
        "Setting Type = Competition is what makes the **Judging** button appear on every cohort of this "
        "program, and what allows team-shared checklist steps. If Judging is missing later, this is the "
        "first thing to check.",
    )

    # ── 3. Cohorts ───────────────────────────────────────────────────
    g.h1("3. Create one cohort per phase")
    g.para(
        "Every phase of the competition is its own cohort under the same program. This is not a naming "
        "convention — teams, checklists, judges, scores and publication are **all** cohort-scoped, so a "
        "phase that isn't its own cohort cannot be judged or published separately."
    )
    g.steps([
        "Go to **Operations → Cohorts** (`/operations/cohorts`) and click **New cohort**.",
        "Pick the competition **Program** you just created.",
        "**Name** it after the phase — *Qualifiers*, *Semi-finals*, *Finals*. Keep the names distinct; students and judges see them.",
        "Set **Starts on** / **Ends on** to that phase's window, and **Capacity** if you want a cap.",
        "Set **Visibility** to *Private* — a competition roster comes from your import, not from public sign-ups.",
        "Set **Status** appropriately and click **Create cohort**.",
        "Repeat for every phase. Create them all up front if you can: the *Advance teams* control at the end only offers cohorts that already exist.",
    ])
    g.screenshot(
        "The cohort list showing all phases of the competition",
        where="Operations → Cohorts, filtered to the competition program",
        annotate=[
            "Highlight the three phase cohorts under one program.",
            "Point at the program filter dropdown used to get this view.",
        ],
    )
    g.callout(
        "Watch out",
        "A team belongs to one cohort for good — a Qualifiers team is never reused in Finals. Advancing "
        "creates a **new team with the same name** in the target cohort and re-registers each member there. "
        "That is expected, not a duplicate to clean up.",
    )

    # ── 4. LMS program ───────────────────────────────────────────────
    g.h1("4. Create the LMS program (the checklist)")
    g.para(
        "The LMS program is the container for the steps students work through. It is created once against "
        "the program and then tailored per cohort in the next section."
    )
    g.steps([
        "Go to **LMS Programs** (`/lms-authoring/curriculum`).",
        "Pick your competition program from the list at the top.",
        "If it has no checklist yet you'll see *This program has no LMS checklist yet* — type a name (e.g. *Ru'ya Space Race — Steps*) and click **Create checklist**.",
        "On the **Program** tab you can toggle **Gate certificate on this checklist** if the cohort's certificate should require every non-optional step.",
    ])
    g.screenshot(
        "Creating the checklist for the competition program",
        where="LMS Programs → (select program) → Create checklist",
        annotate=["Point at the program picker and the Create checklist button."],
    )

    # ── 5. Cohort checklists ─────────────────────────────────────────
    g.h1("5. Build each cohort's checklist — not the program's")
    g.para(
        "The tab row across the top of LMS Programs is: **Program**, then one tab per cohort. The Program tab "
        "is the master template. Each cohort tab shows that template **until you edit it** — the first edit "
        "creates that cohort's own override, which from then on is what its students see."
    )
    g.callout(
        "Rule",
        "For a competition, build the real steps on **each cohort tab**, not on the Program tab. Phases have "
        "genuinely different deliverables (Qualifiers ≠ Finals), and once a cohort has its own override, later "
        "edits to the program template no longer reach it.",
    )
    g.para(
        "You will see a grey banner reading *Showing the program's own checklist — edit anything below to start "
        "this cohort's own override* while a cohort is still inheriting. Once you add or change a step, that "
        "banner disappears: you are now editing that cohort alone."
    )
    g.screenshot(
        "The cohort tab row with the inheritance banner",
        where="LMS Programs → your program → a cohort tab → Checklist",
        annotate=[
            "Circle the cohort tabs (Program | Qualifiers | Finals).",
            "Underline the *edit anything below to start this cohort's own override* banner.",
        ],
    )

    g.h2("Adding steps")
    g.steps([
        "Open the cohort tab, stay on the **Checklist** sub-tab.",
        "Under **Add a step**, click the type you want (see the table below).",
        "Give it a **Title** and, optionally, a **Description** — both are shown to the student.",
        "Tick **Optional** if it shouldn't count toward completion, and **Needs instructor/ops confirmation** if a human has to sign it off after the student marks it done.",
        "Click **Save**. Drag the rows by their handle to reorder — the order is the order students see.",
    ])
    g.table(
        ["Step type", "What the student does", "Use it for"],
        [
            ["Course", "Works through an LMS course", "Required learning before a deliverable"],
            ["Mission run", "Opens and completes a Design or Operate mission", "SatKit design / operations work"],
            ["Link", "Opens a URL, then marks it done", "Google Forms quizzes, briefs, external resources"],
            ["Individual Submission", "Pastes their own link", "Anything each student owes personally"],
            ["Team Submission", "**One shared link for the whole team**", "Poster, presentation video, Tinkercad circuit, CAD, dashboard"],
            ["PDF", "Reads a PDF you upload, then marks it done", "Rules, brief, judging criteria hand-out"],
            ["Manual check-off", "Just ticks it", "Attendance, kit collected, anything tracked off-platform"],
        ],
        widths=[1.5, 2.3, 2.7],
    )
    g.screenshot(
        "The Add a step row with all step types visible",
        where="LMS Programs → cohort tab → Checklist → Add a step",
        annotate=[
            "Circle **Team Submission** and **Individual Submission** as two separate buttons.",
            "Point at the Optional / Needs confirmation checkboxes on the open form.",
        ],
    )
    g.callout(
        "Watch out",
        "**Individual vs Team is fixed when the step is created.** That is why they are two separate buttons "
        "rather than a checkbox you can flip afterwards — the two scopes store their submissions in different "
        "places, so switching would orphan anything already submitted. To change it, delete the step and add it "
        "again with the right type (anything already submitted against it is lost, so do this before the phase opens).",
    )
    g.para(
        "For a **Team Submission** step, fill the *What should the student submit back?* prompt — that text is "
        "what the team reads next to the link box. A reference link (the template, the brief) is optional and "
        "shown alongside it."
    )

    g.h2("Mission runs and per-cohort gating")
    g.para(
        "Mission steps have their own **Missions** sub-tab. Add the mission run there, then use its two tabs to "
        "control the run for **this cohort only**: which build steps apply, and which of them are unlocked. "
        "Gating is always cohort-specific — the same mission can be tighter in Qualifiers than in Finals."
    )
    g.screenshot(
        "A mission run's per-cohort steps and gates",
        where="LMS Programs → cohort tab → Missions → (expand a mission run)",
        annotate=["Point at the Steps and Gates tabs.", "Circle one locked vs one unlocked step."],
    )

    g.h2("Changing the checklist after students are already on it")
    g.bullets([
        "**Adding a step is safe at any time.** New steps backfill automatically to students who are already assigned.",
        "If someone reports a step they can't see, open the cohort's **Checklist** sub-tab and click **Resync students**. It reports how many missing items it caught up (it says *Every assigned student is already caught up* when there is nothing to do).",
        "**Editing** a step's title, description, prompt, optional or confirmation flag takes effect immediately for everyone.",
        "**Deleting** a step deletes what students did against it. Do it before the phase opens, not during.",
        "**Reordering** is cosmetic and safe.",
        "Edits made on a cohort tab affect that cohort only. Edits on the **Program** tab only reach cohorts that have never been edited.",
    ])

    # ── 6. Roster import ─────────────────────────────────────────────
    g.h1("6. Import the teams")
    g.para(
        "Registration and shortlisting happen off-platform (Google Forms). The platform's job starts when you "
        "have a final roster. Everything below happens on **one cohort** — the phase you are opening."
    )
    g.steps([
        "Open the cohort: **Operations → Cohorts → (the phase)**, then click **Judging** in the header.",
        "Stay on the **Roster** tab and click **Upload roster**. `.xlsx`, `.xls` and `.csv` are all accepted.",
        "Review the **preview table** that appears — nothing has been created yet at this point.",
        "Fix anything flagged (you can type directly into any cell), then click **Confirm import**.",
        "Read the per-row result table: *created*, *matched*, or an error with the reason.",
    ])
    g.h2("What the sheet needs")
    g.table(
        ["Column", "Required", "Notes"],
        [
            ["`team_name`", "Yes", "Rows sharing a name become one team"],
            ["`member_name`", "Yes", "Also accepted as *Student Name*"],
            ["`email`", "Yes", "Becomes the student's login"],
            ["`phone`", "No", "Stored on the contact"],
            ["`school`", "No", "Also accepted as *School / University*"],
        ],
        widths=[1.3, 0.9, 4.3],
    )
    g.para(
        "A title row or a stage-description row above the real header is fine — the importer scans the first ten "
        "rows for the header. One row per **member**, not per team."
    )
    g.screenshot(
        "The roster preview with a blocked row and a flagged row",
        where="Cohort → Judging → Roster, after uploading the sheet",
        annotate=[
            "Point at a red row: *won't import until fixed* (a required field is empty).",
            "Point at an amber row: flagged email — importable as-is, or fix it here.",
            "Circle **Confirm import**.",
        ],
    )
    g.table(
        ["Row colour", "Meaning", "What to do"],
        [
            ["Red", "Team name, member name or email is missing", "Type the value into the cell — the row won't import without it"],
            ["Amber", "The email doesn't look valid", "Fix it, or import as-is and correct that student later"],
            ["Plain", "Nothing wrong", "Nothing"],
        ],
        widths=[0.9, 2.6, 3.0],
    )
    g.h2("What confirming actually does, per row")
    g.bullets([
        "Finds or creates the **contact**, then registers them on this cohort.",
        "Finds or creates their **student account** and emails them a set-password link (valid **3 days**).",
        "Assigns them this cohort's **checklist**, enrolling any course steps and creating any mission attempts.",
        "Finds or creates the **team** by name in this cohort and adds them to it.",
    ])
    g.callout(
        "Note",
        "The import is **idempotent**. Re-uploading the same sheet reports every row as *matched* and creates "
        "nothing new — so a corrected sheet can safely be re-run in full.",
    )

    # ── 7. Teams tab ─────────────────────────────────────────────────
    g.h1("7. Fix the roster by hand")
    g.para(
        "The **Teams** tab is for one-off corrections after an import — a late sign-up, a team split, someone "
        "switching teams — without re-uploading a whole sheet."
    )
    g.bullets([
        "**Add team** — type a name and click Add team.",
        "**Add member** — name + email on the team card. A new email creates and invites the account; a known email is matched, exactly like a roster row.",
        "**Rename** (pencil) and **delete** (bin) a team; remove a member with the icon beside their name.",
        "Click a member's name to open their profile.",
    ])
    g.screenshot(
        "The Teams tab with one team card expanded to add a member",
        where="Cohort → Judging → Teams",
        annotate=["Circle **Add member**.", "Point at the rename and delete icons on the team header."],
    )
    g.callout(
        "Watch out",
        "Deleting a team removes its shared team submissions with it. If a team simply changed name, rename it "
        "instead of deleting and re-creating.",
    )

    # ── 8. Rubric ────────────────────────────────────────────────────
    g.h1("8. Write the rubric")
    g.para(
        "The rubric is **program-scoped**: one rubric serves every phase of the competition. Editing it from the "
        "Finals cohort edits the same rubric the Qualifiers judges used."
    )
    g.steps([
        "Go to **Cohort → Judging → Rubric**.",
        "Set the **Rubric name** (shown to judges).",
        "Click **Add criterion** for each line: a **key** (short, no spaces — `design`, `innovation`), a **Label** (what judges read) and **max points**.",
        "The total updates as you type — check it matches what was published to the teams.",
        "Click **Save rubric**.",
    ])
    g.screenshot(
        "A saved rubric with its criteria and total",
        where="Cohort → Judging → Rubric",
        annotate=["Circle the *Criteria · N pts total* line.", "Point at one row's key / label / max points."],
    )
    g.callout(
        "Watch out",
        "Saving rewrites the whole rubric: a criterion you removed from the list is deleted. Don't restructure a "
        "rubric mid-phase — judges' scores are stored against criterion keys, and changing the keys invalidates "
        "what has already been scored. Set it before inviting judges.",
    )

    # ── 9. Judges ────────────────────────────────────────────────────
    g.h1("9. Invite the judges")
    g.para("Judges are added **per cohort**. A judge added to Qualifiers cannot see Finals, and vice versa.")
    g.steps([
        "Go to **Cohort → Judging → Judges**.",
        "To use an existing staff account, type two or more characters in **Search staff by name or email** and pick them — the name and email fill in for you.",
        "For an external judge, type their **Name** and **Email** directly.",
        "Click **Add as judge**. They receive an email with a set-password link, valid **3 days**.",
        "Repeat for every judge on this phase.",
    ])
    g.screenshot(
        "The Judges tab with judges added and their scoring counts",
        where="Cohort → Judging → Judges",
        annotate=[
            "Point at the *N / M teams scored* counter on a judge row.",
            "Circle the staff search box and the manual name/email fields.",
        ],
    )
    g.h2("Removing a judge")
    g.table(
        ["Situation", "What to do", "Effect"],
        [
            ["Wrong cohort / no longer judging this phase", "The bin icon on their row (**Remove**)", "Removes this cohort only. Their account and any scores stay; they can be re-added later."],
            ["Should not access the platform at all any more", "**Users → deactivate** the account", "Blocks login immediately without touching their scores. This is the correct way to retire a judge who has scored."],
            ["Created by mistake, never scored", "Delete the user from Users", "Only possible while they have no scores — the system refuses once they have scored anything."],
        ],
        widths=[1.7, 1.8, 3.0],
    )
    g.callout("Note", "Send judges the **Judge Guide** with their invite — it is the one-page version of what they need.")

    # ── 10. Tracking ─────────────────────────────────────────────────
    g.h1("10. Track progress while the phase runs")
    g.para("Three places, three questions.")

    g.h2("a) Are the teams doing the work? — checklist progress")
    g.steps([
        "**LMS Programs → your program → the cohort tab → Progress**.",
        "Each student row shows *items done / total* and a percentage bar; the certificate badge appears when the program gates certificates on the checklist.",
        "Click the arrow on the left of a row to expand it — every step with its status, and a **submission** link where one was submitted.",
        "Anything a student marked done on a *Needs confirmation* step shows a **Confirm: <step>** button on their row. Click it to sign it off.",
    ])
    g.screenshot(
        "A student's expanded progress row",
        where="LMS Programs → cohort tab → Progress",
        annotate=[
            "Point at the progress bar and the done/total count.",
            "Circle a **Confirm:** button.",
            "Point at a step's *submission* link and a mission step's **view run** link.",
        ],
    )

    g.h2("b) How are the missions going? — mission progress")
    g.para(
        "Two views, use whichever suits the question:"
    )
    g.bullets([
        "**Inside the cohort** — on the same expanded Progress row, a mission step shows **view run**, which opens that student's actual mission run read-only. Use this when someone reports being stuck.",
        "**Across everything** — **LMS Programs → Progress** (`/lms-authoring/progress`) has a **Missions** tab: every mission, its attempt counts, and a per-student table you can filter by program and cohort. Use this to see who has not started.",
        "The **Review** sub-tab on a cohort is where Design mission runs land. A Design run passes on its own once every step is valid; **Force pass/fail** (a reason is required) is only for unblocking someone stuck on a mistake, not routine grading.",
    ])
    g.table(
        ["Mission status", "Meaning"],
        [
            ["In progress", "Started, not finished"],
            ["Submitted", "Sent for review / awaiting the automatic check"],
            ["Passed", "Complete"],
            ["Failed", "Did not pass — the student can normally try again"],
            ["Abandoned", "Attempt was dropped"],
        ],
        widths=[1.4, 5.1],
    )
    g.screenshot(
        "The Missions progress tab for the competition cohort",
        where="LMS Programs → Progress → Missions",
        annotate=["Point at the program/cohort filters.", "Circle a student sitting at *In progress* while others passed."],
    )

    g.h2("c) Are the judges done? — scoring progress")
    g.para(
        "**Cohort → Judging → Judges** shows *N / M teams scored* for each judge. That counter only moves when a "
        "judge clicks **Submit score** — a judge's autosaved draft does **not** count, and does not affect the "
        "leaderboard. Chase anyone whose counter is short before you publish."
    )
    g.para(
        "The **Results** tab's *Per judge* column shows who scored what for each team, and *Not scored yet* where "
        "nobody has. Between the two you can see exactly what is outstanding."
    )
    g.screenshot(
        "The Results leaderboard mid-phase, with gaps",
        where="Cohort → Judging → Results",
        annotate=["Point at a team showing *Not scored yet*.", "Point at the per-judge score pills on a scored team."],
    )

    # ── 11. Publish ──────────────────────────────────────────────────
    g.h1("11. Publish the results")
    g.para(
        "Publishing is the gate that closes scoring. Do it once every judge's counter reads *M / M teams scored*."
    )
    g.steps([
        "Go to **Cohort → Judging → Results** and check the leaderboard is complete.",
        "Click **Publish results**. The pill at the top changes to *Published* with the date.",
        "From that moment every judge on this cohort is read-only — an attempt to save a score is refused.",
        "If you published too early, click **Unpublish**: scoring reopens for everyone and the results are no longer final.",
    ])
    g.table(
        ["Control", "What it does"],
        [
            ["**Publish results**", "Closes scoring for every judge on this cohort. Reversible with Unpublish."],
            ["**Filter to Top 20**", "Filters the table on screen to the 20 highest-ranked teams. Downloads nothing."],
            ["**Export spreadsheet**", "Downloads an `.xlsx` with a **Scores** sheet (rank, average, status, each judge's total) and a **Submissions** sheet (every team's links, who submitted and when)."],
        ],
        widths=[1.6, 4.9],
    )
    g.callout(
        "Note",
        "A team's score is the **average of every judge's submitted total** for that phase. Teams nobody has "
        "scored rank last as *unscored*. Judges never see each other's scores — only you see the per-judge "
        "breakdown, and publishing does not change that.",
    )
    g.callout(
        "Watch out",
        "Publishing does **not** notify students and does not show them a leaderboard — there is no student-facing "
        "results page. Announcing results is a separate, off-platform step. The one message the platform sends is "
        "the congratulations email when you advance a team (next section).",
    )
    g.screenshot(
        "The Results tab published, with the export button",
        where="Cohort → Judging → Results",
        annotate=["Circle the *Published · date* pill.", "Point at **Export spreadsheet** and **Filter to Top 20**."],
    )

    # ── 12. Advance ──────────────────────────────────────────────────
    g.h1("12. Advance teams to the next phase")
    g.para(
        "Choosing who goes through is your decision, made off-platform (typically by exporting the Top 20 for "
        "external review). Nothing advances automatically off a score threshold — selecting the rows **is** the "
        "confirmation."
    )
    g.steps([
        "On **Results**, tick the checkbox beside each team that goes through.",
        "Pick the target phase in the **Advance to…** dropdown (it lists the other cohorts of this program).",
        "Click **Advance selected teams**.",
        "Each advanced team gets an **Advanced** badge on the leaderboard; every member receives a congratulations email naming the next phase.",
    ])
    g.para("For each member of each selected team, advancing registers them on the target cohort, assigns that cohort's checklist, and puts them in a new same-named team there.")
    g.screenshot(
        "Selecting teams and choosing the target phase",
        where="Cohort → Judging → Results",
        annotate=[
            "Tick a few team checkboxes.",
            "Circle the **Advance to…** dropdown and the **Advance selected teams** button.",
            "Point at an **Advanced** badge on an already-advanced team.",
        ],
    )
    g.table(
        ["If you see…", "It means"],
        [
            ["*No other cohort exists yet under this program*", "Create the next phase's cohort first (Operations → Cohorts); the control then appears here."],
            ["An error naming the source cohort", "One of the selected teams is not actually in this cohort. Re-check the selection."],
            ["Nothing happens on click", "Either no teams are ticked or no target phase is selected — both are required."],
        ],
        widths=[2.5, 4.0],
    )
    g.callout(
        "Note",
        "Advancing the same team twice is harmless — members already registered on the target cohort are left "
        "as they are. Students keep their old team card in Learn as well as the new one; the phase name on the "
        "card is what tells them apart.",
    )

    # ── 13. Next phase ───────────────────────────────────────────────
    g.h1("13. Run the next phase")
    g.para(
        "The next phase is the same cohort-scoped loop, on its own cohort: build its checklist (section 5), skip "
        "the roster import if everyone arrived by advancing, invite its judges (section 9), track (section 10), "
        "publish (section 11)."
    )
    g.bullets([
        "The **rubric is already there** — it is program-wide. Only change it if the criteria genuinely change, and never mid-phase.",
        "**Judges are not carried over.** Add judges to the new cohort explicitly, even if they are the same people.",
        "**Publication is per phase.** Publishing Qualifiers has no effect on Finals.",
        "Teams that were advanced are already registered and already have the new checklist. Use the **Teams** tab only for late additions.",
    ])

    # ── 14. Troubleshooting ──────────────────────────────────────────
    g.h1("14. Troubleshooting")
    g.table(
        ["Symptom", "Cause", "Fix"],
        [
            ["No **Judging** button on the cohort", "The program's Type isn't Competition", "Operations → Programs → edit the program → Type = Competition"],
            ["The upload fails with *Failed to read this file*", "Not a readable .xlsx/.xls/.csv, or the header row is missing", "Re-export from Sheets/Excel; make sure `team_name`, `member_name` and `email` columns exist"],
            ["A student says they never got an email", "Wrong address on the row, or it went to spam", "Fix the email on the Teams tab, or resend the invite from LMS Programs → Students"],
            ["A student's set-password link doesn't work", "The link is older than 3 days", "Resend the invite — a fresh link is generated each time"],
            ["A student can't see a step you added", "Their assignment predates the step", "Cohort tab → Checklist → **Resync students**"],
            ["A team submission shows the wrong link", "A teammate replaced it — that is by design", "Any member can submit again; the newest link wins. The caption shows who submitted it and when"],
            ["A judge sees *No rubric configured*", "The rubric was never saved for this program", "Judging → Rubric → add criteria → Save rubric"],
            ["A judge sees *No competitions assigned yet*", "They were never added to this cohort", "Judging → Judges → Add as judge"],
            ["A judge can't save a score", "The cohort's results are published", "Unpublish on the Results tab, let them finish, publish again"],
            ["A team is missing from the leaderboard", "It has no members, or it belongs to another cohort", "Check the Teams tab of the right cohort"],
            ["A team shows *Not scored yet* though the judge scored it", "The judge left it as an autosaved draft", "Ask them to open the team and click **Submit score**"],
            ["**Advance to…** is empty", "No sibling cohort exists", "Create the next phase's cohort first"],
        ],
        widths=[2.1, 1.9, 2.5],
    )

    # ── Appendix ─────────────────────────────────────────────────────
    g.h1("Appendix A — Screens and where they live")
    g.table(
        ["Screen", "Path", "Who can open it"],
        [
            ["Programs", "`/operations/programs`", "operations, admin"],
            ["Cohorts", "`/operations/cohorts`", "operations, admin"],
            ["Cohort detail (has the **Judging** button)", "`/operations/cohorts/<id>`", "operations, admin"],
            ["Judging (Roster / Teams / Rubric / Judges / Results)", "`/operations/cohorts/<id>/judging`", "operations, admin"],
            ["LMS Programs (checklists, missions, progress, review)", "`/lms-authoring/curriculum`", "operations, facilitator, admin; instructors see their own cohorts only"],
            ["Progress grid (courses & missions)", "`/lms-authoring/progress`", "operations, facilitator, admin"],
            ["Students (invites, password resets)", "`/lms-authoring/students`", "operations, facilitator, admin"],
            ["Judge area", "`/judge`", "judge only"],
            ["Student area", "`/learn`", "students"],
        ],
        widths=[2.6, 2.2, 1.7],
    )

    g.h2("Appendix B — Emails the platform sends")
    g.table(
        ["When", "To", "Contains"],
        [
            ["A roster row creates a new account", "That student", "*Your SpacePoint learning account* — a set-password link valid 3 days"],
            ["A judge is added and is new", "That judge", "The same set-password email, pointing at the portal login"],
            ["A team is advanced", "Every member of that team", "*You're through to the next stage!* naming the team and the next phase"],
        ],
        widths=[2.1, 1.6, 2.8],
    )
    g.para(
        "Nothing else is sent automatically — in particular, publishing results sends no email.",
        color=None,
    )

    return g.save(OUT)


if __name__ == "__main__":
    print(build())
