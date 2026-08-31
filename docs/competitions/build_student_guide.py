"""Builds "Competitions — Student Guide" (.docx, on the SPACE. letterhead)."""

from pathlib import Path

from guide_kit import Guide

OUT = Path(__file__).parent / "Competitions - Student Guide.docx"


def build() -> Path:
    g = Guide(
        "Competitions — Student Guide",
        "Your account, your team's checklist, and how to hand work in",
        [
            ("Audience", "Students taking part in a SpacePoint competition"),
            ("You need", "The email SpacePoint sent you, and a browser (a laptop is easiest for submissions)"),
            ("Covers", "Setting your password → finding your team → working the checklist → submitting → courses and missions → moving to the next stage"),
            ("Version", "1.0  ·  31 August 2026"),
        ],
    )

    # ── 1. Overview ──────────────────────────────────────────────────
    g.h1("1. How the competition works on the platform", page_break=False)
    g.para(
        "Everything you have to do in this competition is listed in one place: your team's **checklist**. It "
        "shows every step in order — things to read, courses to complete, missions to fly, and the work your "
        "team has to hand in — and it shows what is done and what is still open."
    )
    g.bullets([
        "You get **one account**, created for you from the registration sheet. You don't sign up yourself.",
        "You are on **one team** per stage of the competition, with the teammates the organisers assigned you.",
        "Some steps are **yours alone**. Others are **shared with your team** — one submission covers all of you.",
        "If your team goes through to the next stage, a **new checklist** appears for it.",
    ])

    # ── 2. Account ───────────────────────────────────────────────────
    g.h1("2. Set your password and log in")
    g.steps([
        "Look for the email titled **Your SpacePoint learning account** (check your spam folder if it isn't in your inbox). It says an account was created for you and has a link to set your password.",
        "Open the link. It works for **3 days** — after that, ask the organisers to send a new one.",
        "Choose a password, type it again to confirm, and continue.",
        "When you see **Password set**, click **Go to login**.",
        "Log in with your **email address** and your new password.",
    ])
    g.screenshot(
        "The set-your-password screen",
        where="The link in your invitation email",
        annotate=["Point at the password and confirm boxes.", "Circle the button that saves it."],
    )
    g.callout(
        "Watch out",
        "Use the same email address the competition was registered with. If you set up a different account "
        "yourself, it won't be linked to your team and your checklist won't be there.",
    )

    # ── 3. Home ──────────────────────────────────────────────────────
    g.h1("3. Find your team and your checklist")
    g.para(
        "After logging in you land on the Learn home page. Look for the **My Team** card: it shows your team "
        "name, your teammates, and the stage it belongs to."
    )
    g.steps([
        "Click **Open checklist** on the My Team card.",
        "Alternatively, use **Programs** in the top menu, which lists every checklist you have.",
    ])
    g.para(
        "If the card says *No checklist yet — check back soon*, your team exists but the organisers haven't "
        "opened the steps yet."
    )
    g.screenshot(
        "The My Team card on the Learn home page",
        where="Learn home, straight after logging in",
        annotate=[
            "Circle the team name and the stage name beside *My Team*.",
            "Circle **Open checklist**.",
            "Point at **Programs** in the top menu.",
        ],
    )
    g.callout(
        "Note",
        "The other things on this page — **My Learning**, **Missions**, **Live Quiz**, **Leaderboard** — are the "
        "general learning platform. Your competition work is all reached through the checklist.",
    )

    # ── 4. Checklist ─────────────────────────────────────────────────
    g.h1("4. Work through the checklist")
    g.para(
        "The checklist is a numbered list of steps in the order you should do them. At the top you'll see how "
        "many steps are done out of the total, and a progress bar. The step you should be doing next is "
        "highlighted and marked **Up next**."
    )
    g.h2("Reading a step")
    g.table(
        ["On the step", "What it tells you"],
        [
            ["A **type** label (Course, Mission run, Link, Submission, PDF, Manual check-off)", "What kind of step it is — see the next section"],
            ["A **Team** tag", "This one is shared with your whole team: one submission covers all of you"],
            ["*optional*", "Doesn't count toward finishing the checklist, but is still worth doing"],
            ["**Up next**", "The first step you haven't finished"],
            ["**Awaiting confirmation**", "You marked it done; a member of staff still has to sign it off"],
            ["**Complete**", "Finished"],
        ],
        widths=[2.7, 3.8],
    )
    g.screenshot(
        "Your team's checklist",
        where="Learn home → My Team → Open checklist",
        annotate=[
            "Point at the steps-done counter and the progress bar.",
            "Circle a step tagged **Team**.",
            "Circle the step marked **Up next**.",
        ],
    )

    g.h2("What to do for each type of step")
    g.table(
        ["Type", "What you do"],
        [
            ["**Course**", "Click the step to open the course, then work through its modules. Your progress saves as you go."],
            ["**Mission run**", "Click the step to open the mission and work through it. It marks itself complete when you finish."],
            ["**Link**", "Open the link (often a form or quiz), do what it asks, come back and click **Mark as done**."],
            ["**PDF**", "Click **Open the PDF** to read it, then click **Mark as done**."],
            ["**Manual check-off**", "Nothing to hand in — click **Mark as done** when you've done it."],
            ["**Submission**", "Paste a link to your work in the box and click **Submit**. See the next section."],
        ],
        widths=[1.5, 5.0],
    )
    g.callout(
        "Note",
        "If a button reads **Mark as done (needs sign-off)**, clicking it puts the step into *Awaiting "
        "confirmation*. That's normal — a member of staff completes it from their side.",
    )

    # ── 5. Submissions ───────────────────────────────────────────────
    g.h1("5. Hand your work in")
    g.para(
        "Competition deliverables — poster, presentation video, circuit, CAD design, dashboard — are handed in "
        "as **links**, not uploads. Put your file somewhere the judges can open it, then paste the link."
    )
    g.steps([
        "Read the prompt on the step: it says exactly what to submit.",
        "Put the work somewhere shareable (Google Drive, Canva, YouTube, Tinkercad, your hosted page…).",
        "**Make sure the link is viewable by anyone with the link.** A judge who can't open it can't score it.",
        "Paste the link into the box on the step and click **Submit**.",
        "Check the confirmation line that appears under the step — it shows the link, the time and who submitted it.",
    ])
    g.screenshot(
        "A team submission step with a link submitted",
        where="Your checklist → a step tagged **Team**",
        annotate=[
            "Point at the prompt describing what to submit.",
            "Circle the link box and the **Submit** button.",
            "Underline the *Submitted … by …* confirmation line.",
        ],
    )
    g.h2("Team submissions — read this with your team")
    g.bullets([
        "**Any teammate can submit** a team step. You don't have to be the same person each time.",
        "**The newest link replaces the old one.** If a teammate submits after you, theirs is what the judges see.",
        "The line under the step always shows the link that is currently in, **who** submitted it and **when** — so check there before submitting again.",
        "You can replace a link at any time until the organisers close the stage, even after the step shows as complete. The button reads **Replace submission** once something is in.",
        "Agree inside your team who submits what, so you don't overwrite each other by accident.",
    ])
    g.callout(
        "Watch out",
        "Submitting a link is the only thing that counts as handing work in. A file sitting in your Drive that "
        "was never linked on the checklist has not been submitted, and the judges will not see it.",
    )

    # ── 6. Courses and missions ──────────────────────────────────────
    g.h1("6. Courses and missions")
    g.h2("Courses")
    g.para(
        "A **Course** step opens a course made of modules — short videos and checks. Work through it at your "
        "own pace; your place is saved, so you can stop and come back. The step ticks itself off when you "
        "have completed what the course requires. **My Learning** in the top menu lists every course you are on."
    )
    g.h2("Missions")
    g.para(
        "A **Mission run** step opens a mission — the hands-on design or operations work. Everything you do "
        "inside it is saved as you go, and the step completes on its own when the mission is finished. Some "
        "missions unlock step by step, so a later part may not be available until you finish an earlier one."
    )
    g.bullets([
        "Missions are done on **your own account**, even when the rest of the stage is team work.",
        "Your instructors can open your mission run to see where you are, so if you are stuck, ask — they can see exactly what you see.",
        "If a mission doesn't pass, you can normally try again. Check with your instructors before starting over.",
    ])
    g.screenshot(
        "A mission opened from the checklist",
        where="Your checklist → a **Mission run** step",
        annotate=["Point at where progress is shown.", "Circle any locked step, if one is visible."],
    )

    # ── 7. Next stage ────────────────────────────────────────────────
    g.h1("7. Moving to the next stage")
    g.para(
        "Results are decided by the judges and announced by the organisers — there is no scoreboard for you to "
        "check in the platform, and no scores are shown to students."
    )
    g.bullets([
        "If your team goes through, every member gets an email: **You're through to the next stage!**",
        "Log in and you'll see a **new My Team card** for the next stage, with its own checklist.",
        "Your old team card stays as well — the stage name on the card tells them apart. Always work from the newest one.",
        "Your old checklist stays readable, so nothing you did is lost.",
    ])
    g.callout("Tip", "Check the stage name on the card before starting work, so you're not filling in last stage's checklist.")

    # ── 8. FAQ ───────────────────────────────────────────────────────
    g.h1("8. Common questions")
    g.table(
        ["Question", "Answer"],
        [
            ["I never got the email", "Check spam. If it isn't there, ask the organisers to resend the invite to the address on your registration"],
            ["The password link doesn't work", "It expired (3 days). Ask for a new one — each one is fresh"],
            ["I can log in, but there's no team card", "Your account may not be linked to the roster. Tell the organisers which email you're logged in with"],
            ["A step my teammate says exists isn't on my list", "Refresh the page; if it's still missing, tell the organisers — they can resync your checklist"],
            ["My teammate replaced my submission", "That's how team steps work — the newest link wins. Agree between you who submits, then submit again if it was a mistake"],
            ["Can I change a submission after marking it done?", "Yes, until the organisers close the stage. Use **Replace submission**"],
            ["I finished the work but the step is stuck on *Awaiting confirmation*", "That step needs staff sign-off. Nothing more for you to do"],
            ["Can I see our score?", "No. Judges' scores are never shown to students; the organisers announce results"],
            ["Can I use my phone?", "For reading and marking steps, yes. For submissions and missions, a laptop is much easier"],
        ],
        widths=[2.4, 4.1],
    )
    g.callout(
        "Rule",
        "Before a deadline, open your checklist and check that every step you owe shows a submitted link or a "
        "**Complete** badge. What is on the checklist is what the judges see.",
    )

    return g.save(OUT)


if __name__ == "__main__":
    print(build())
