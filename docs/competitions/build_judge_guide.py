"""Builds "Competitions — Judge Guide" (.docx, on the SPACE. letterhead)."""

from pathlib import Path

from guide_kit import Guide

OUT = Path(__file__).parent / "Competitions - Judge Guide.docx"


def build() -> Path:
    g = Guide(
        "Competitions — Judge Guide",
        "Getting into the platform, reviewing your teams and scoring them",
        [
            ("Audience", "Invited competition judges"),
            ("You need", "The invitation email SpacePoint sent you, and a browser"),
            ("Covers", "Setting your password → finding your teams → reading their submissions → scoring → submitting"),
            ("Time", "About 5 minutes to set up; scoring takes as long as the work deserves"),
            ("Version", "1.0  ·  31 August 2026"),
        ],
    )

    # ── 1. What judging looks like ───────────────────────────────────
    g.h1("1. What you'll be doing", page_break=False)
    g.para(
        "You have been given a judge account for **one stage** of a competition. Inside it you will see the "
        "teams competing in that stage, everything each team submitted, and a scoring form built from the "
        "competition's rubric."
    )
    g.h2("What you can see")
    g.bullets([
        "The teams in the stage you were added to, and their members' names.",
        "Every deliverable those teams submitted — the link, who submitted it, and when.",
        "The rubric, and **your own** scores.",
    ])
    g.h2("What you can't see")
    g.bullets([
        "**Other judges' scores.** Scoring is blind, and stays blind even after results are finalised.",
        "The overall standings or averages.",
        "Any other stage of the competition, or anything else in the platform.",
    ])
    g.callout(
        "Note",
        "Score each team on its own merits. Because you never see another judge's numbers, there is nothing "
        "to calibrate against mid-round — the organisers combine the judges' scores afterwards.",
    )

    # ── 2. Getting in ────────────────────────────────────────────────
    g.h1("2. Get into your account")
    g.steps([
        "Find the email titled **Your SpacePoint learning account**. It says an account was created for you and carries a *Set your password* link. The link is valid for **3 days** — if yours has expired, ask the organisers to resend it.",
        "Click the link, choose a password, confirm it, and click through.",
        "You'll see **Password set**. Click **Go to login**.",
        "Log in with your **email address** and the password you just set.",
        "You land on **Teams to judge**. That is your whole workspace — judges have no other pages.",
    ])
    g.screenshot(
        "The set-password screen",
        where="The link in your invitation email",
        annotate=["Point at the password and confirm fields.", "Circle the button that finishes setup."],
    )
    g.callout(
        "Tip",
        "Bookmark the page you land on after logging in. If you are ever logged out mid-scoring, log back in "
        "and everything you had saved is still there.",
    )

    # ── 3. Your teams ────────────────────────────────────────────────
    g.h1("3. Find your teams")
    g.para(
        "**Teams to judge** lists every team in your stage. The stage's name is shown under the page title, "
        "and each row shows the team name, its members, and whether you have scored it."
    )
    g.table(
        ["What you see", "What it means"],
        [
            ["**Scored** (green tick)", "You have submitted a score for this team"],
            ["**Not scored**", "You have not submitted a score yet — a saved draft still shows as *Not scored*"],
            ["A row of tabs above the list", "You were added to more than one stage; each tab is one stage"],
            ["*No competitions assigned yet*", "Your account isn't attached to a stage yet — tell the organisers"],
        ],
        widths=[2.0, 4.5],
    )
    g.para("Click any team to open it.")
    g.screenshot(
        "The teams list, with some teams scored and some not",
        where="Teams to judge (the page you land on after login)",
        annotate=["Circle a **Scored** row and a **Not scored** row.", "Point at the stage name under the title."],
    )

    # ── 4. Review ────────────────────────────────────────────────────
    g.h1("4. Review what a team submitted")
    g.para(
        "The team page opens with **Submissions** — every shared deliverable the team was asked for: poster, "
        "presentation video, circuit, CAD design, dashboard, and so on."
    )
    g.bullets([
        "Click **Open** to view a submission. It opens in a new tab, so your scoring form stays where it is.",
        "Under each title you'll see **Submitted <date> by <name>** — the teammate who last submitted it.",
        "**Not submitted** means the team never provided that deliverable. Score it as you would any missing work.",
        "*Nothing submitted yet* means the team has submitted nothing at all.",
    ])
    g.callout(
        "Note",
        "Teams can replace a link at any time until the organisers close the stage, so what you see is always "
        "the latest version. If you reviewed something earlier, check the submitted date before scoring.",
    )
    g.screenshot(
        "A team's submissions list",
        where="Teams to judge → (click a team)",
        annotate=[
            "Point at one submission's **Open** link.",
            "Underline a *Submitted … by …* caption.",
            "Point at an item marked *Not submitted*.",
        ],
    )

    # ── 5. Scoring ───────────────────────────────────────────────────
    g.h1("5. Score the team")
    g.para(
        "Below the submissions is the **Score** section: one row per rubric criterion, each with its maximum "
        "beside the box, plus a **Bonus points** row and a running **Total**."
    )
    g.steps([
        "Type a score into each criterion box. It must be between 0 and the maximum shown to its right.",
        "Add **Bonus points** only if the competition's rules allow them; otherwise leave it at 0.",
        "Check the **Total** — it updates as you type.",
        "Click **Submit score** when you are happy with it.",
    ])
    g.para("The small status line above the scores tells you exactly where your work stands:")
    g.table(
        ["Status line", "What it means"],
        [
            ["**Unsaved changes**", "You just typed something; it saves by itself a moment later"],
            ["**Saving…**", "Being saved right now"],
            ["**Draft saved <time>**", "Safely stored, but **not** counted — the team still shows as *Not scored*"],
            ["**Submitted <time>**", "Done. The team now shows as *Scored* and the organisers can see your total"],
        ],
        widths=[1.9, 4.6],
    )
    g.callout(
        "Rule",
        "**A draft is not a score.** Your typing autosaves so you can stop and come back, on the same device or "
        "another one — but only **Submit score** marks the team as judged. Always finish a team with Submit.",
    )
    g.screenshot(
        "The scoring form with the status line",
        where="Teams to judge → (a team) → Score",
        annotate=[
            "Point at a criterion box and its */ max* label.",
            "Circle the status line (*Draft saved …* or *Submitted …*).",
            "Circle **Submit score** and the running **Total**.",
        ],
    )
    g.h2("Changing a score")
    g.para(
        "Reopen the team, change the numbers, and click **Submit score** again — the new numbers replace the "
        "old ones. You can do this as often as you like until the organisers publish the stage's results."
    )

    # ── 6. When scoring closes ───────────────────────────────────────
    g.h1("6. When scoring closes")
    g.para(
        "Once the organisers **publish** the stage's results, scoring is closed for every judge. If you try to "
        "save after that, you'll see a message saying results are published and scoring is closed."
    )
    g.para(
        "If you still need to change something, contact the organisers — they can reopen the stage, let you "
        "finish, and publish again."
    )

    # ── 7. FAQ ───────────────────────────────────────────────────────
    g.h1("7. If something looks wrong")
    g.table(
        ["What you see", "What to do"],
        [
            ["The invite link says it is invalid or expired", "Ask the organisers to resend it — links last 3 days and a new one is issued each time"],
            ["*No competitions assigned yet*", "You have an account but no stage. The organisers need to add you to one"],
            ["*No teams yet*", "The stage exists but its roster hasn't been imported yet. Check back later"],
            ["*No rubric configured for this competition yet*", "The criteria haven't been set up. Tell the organisers — you can't score until they are"],
            ["A submission link won't open", "The team may have submitted a private or broken link. Note it and tell the organisers; don't guess at the content"],
            ["A team you expected isn't listed", "You may be looking at the wrong stage — check the tabs above the list"],
            ["Your score won't save", "The stage is probably published. Contact the organisers"],
            ["You forgot your password", "Ask the organisers to send a reset link"],
        ],
        widths=[2.4, 4.1],
    )
    g.callout(
        "Tip",
        "Judge one team at a time, end to end: open it, read the submissions, score, **Submit**, go back. "
        "The list's *Scored / Not scored* marks are then an accurate to-do list.",
    )

    return g.save(OUT)


if __name__ == "__main__":
    print(build())
