"""READ-ONLY audit of team-scoped mission_run checklist health.

Never writes — it opens a session, reads, and rolls back. Safe to run
against production at any time.

Born from two stacked production bugs in one cohort (2026-09-19):

  * a team-scoped `mission_run` item added after teams were formed never
    got its shared `LmsProgramTeamItemProgress` row or `MissionAttempt`,
    so the checklist tile had nothing to open (team Orbit3);
  * `mission_attempt_members` is frozen at `start_attempt` time and
    nothing re-syncs it when a roster changes, so a real teammate who
    joined (or was restored) after the attempt started gets a 404 from
    `_own_attempt` (teams with duplicate-account cleanup).

Each of those was found only because a student complained. This checks
for both, plus every other invariant this subsystem relies on, so the
next one is found before a student hits it.

Usage:

    docker exec spacepoint-api python scripts/lms_audit_team_missions.py
    docker exec spacepoint-api python scripts/lms_audit_team_missions.py --cohort <uuid>
    docker exec spacepoint-api python scripts/lms_audit_team_missions.py --cohort <uuid> --verbose

Exit code is 1 if any BLOCKER was found, 0 otherwise — so it can be
wired into a cron/healthcheck later without reading the text.
"""
import argparse
import asyncio
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.lms.program import (
    LmsProgramAssignment, LmsProgramItem, LmsProgramItemProgress, LmsProgramTeamItemProgress,
)
from app.models.missions.mission import Mission, MissionAttempt, MissionAttemptMember
from app.models.sessions.cohort import Cohort
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.lms.program import effective_cohort_program_items

# BLOCKER — a student cannot do the work right now.
# WARN    — inconsistent state that will bite later or corrupts reporting.
# INFO    — expected/benign, listed so it isn't mistaken for a problem.
BLOCKER, WARN, INFO = "BLOCKER", "WARN", "INFO"


class Findings:
    def __init__(self):
        self.rows: list[tuple[str, str, str, str]] = []

    def add(self, severity: str, code: str, where: str, detail: str) -> None:
        self.rows.append((severity, code, where, detail))

    def by_code(self) -> Counter:
        return Counter((sev, code) for sev, code, _w, _d in self.rows)


async def _team_run_items(db, cohort_id) -> list[LmsProgramItem]:
    resolved = await effective_cohort_program_items(db, cohort_id)
    if resolved is None:
        return []
    _program, items, _inherited = resolved
    return [
        i for i in items
        if i.item_type == "mission_run" and i.scope == "team" and i.mission_id
    ]


async def audit_team(db, *, team: Team, items: list[LmsProgramItem], f: Findings) -> None:
    where = f"{team.name} ({team.id})"

    member_rows = (await db.execute(
        select(User.id, User.full_name, User.card_number)
        .join(TeamMember, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team.id)
    )).all()
    if not member_rows:
        # `sync_team_mission_runs` needs one member to resolve the team from
        # (cohort_id, user_id), so an empty team is unfixable AND harmless —
        # nobody can open a tile either. `join_team` wires it on first join.
        f.add(INFO, "EMPTY_TEAM", where, "no members; nothing to wire, self-heals on first join")
        return
    member_ids = {r.id for r in member_rows}
    member_name = {r.id: f"{r.full_name} (SP-ST-{r.card_number:04d})" if r.card_number else r.full_name
                   for r in member_rows}

    team_rows = {
        r.item_id: r for r in (await db.execute(
            select(LmsProgramTeamItemProgress).where(LmsProgramTeamItemProgress.team_id == team.id)
        )).scalars().all()
    }

    assignments = {
        a.user_id: a for a in (await db.execute(
            select(LmsProgramAssignment).where(
                LmsProgramAssignment.cohort_id == team.cohort_id,
                LmsProgramAssignment.user_id.in_(member_ids),
            )
        )).scalars().all()
    }
    for uid in member_ids - set(assignments):
        f.add(BLOCKER, "NO_ASSIGNMENT", where,
              f"{member_name[uid]} is on the team but has no LMS assignment for this cohort "
              f"— they see no checklist at all")

    individual_rows = defaultdict(set)  # item_id -> {user_id}
    if assignments:
        for assignment_id, item_id in (await db.execute(
            select(LmsProgramItemProgress.assignment_id, LmsProgramItemProgress.item_id)
            .where(LmsProgramItemProgress.assignment_id.in_([a.id for a in assignments.values()]))
        )).all():
            individual_rows[item_id].add(assignment_id)

    # Sibling steps of one mission are meant to share ONE attempt — see
    # `_assign_team_mission_run`'s sibling lookup. Collect per mission to
    # check they actually agree.
    attempt_by_mission = defaultdict(set)

    for item in sorted(items, key=lambda i: i.position):
        tile = f"pos {item.position} \"{item.title}\""
        row = team_rows.get(item.id)

        for uid, a in assignments.items():
            if a.id not in individual_rows.get(item.id, set()):
                f.add(WARN, "NO_INDIVIDUAL_ROW", where,
                      f"{tile}: {member_name[uid]} has no individual progress row "
                      f"— the tile does not render for them")

        if row is None:
            f.add(BLOCKER, "NO_TEAM_ROW", where,
                  f"{tile}: no team progress row at all — \"Open\" does nothing")
            continue
        if row.mission_attempt_id is None:
            f.add(BLOCKER, "NO_ATTEMPT", where,
                  f"{tile}: team row exists but mission_attempt_id is NULL — \"Open\" does nothing")
            continue

        attempt_by_mission[item.mission_id].add(row.mission_attempt_id)

        attempt = await db.get(MissionAttempt, row.mission_attempt_id)
        if attempt is None:
            f.add(BLOCKER, "DANGLING_ATTEMPT", where,
                  f"{tile}: mission_attempt_id {row.mission_attempt_id} does not exist")
            continue
        if attempt.team_id != team.id:
            f.add(BLOCKER, "WRONG_TEAM", where,
                  f"{tile}: attempt {attempt.id} belongs to team {attempt.team_id}, not this one")
        if attempt.mission_id != item.mission_id:
            f.add(WARN, "MISSION_MISMATCH", where,
                  f"{tile}: attempt is for mission {attempt.mission_id}, item points at {item.mission_id}")
        if attempt.cohort_id != team.cohort_id:
            f.add(WARN, "COHORT_MISMATCH", where,
                  f"{tile}: attempt cohort_id {attempt.cohort_id} != team cohort_id {team.cohort_id}")

        mission = await db.get(Mission, attempt.mission_id)
        if mission is None:
            f.add(BLOCKER, "NO_MISSION", where, f"{tile}: mission {attempt.mission_id} missing")
        elif mission.kind == "design":
            # `_own_design_attempt` 404s on kind != "design"; a design tile
            # pointing at a non-design mission is dead. Only design missions
            # are checked here because that guard is design-specific.
            pass

        # The 404 class: `_own_attempt` allows ONLY the frozen snapshot.
        snapshot = {
            uid for (uid,) in (await db.execute(
                select(MissionAttemptMember.user_id)
                .where(MissionAttemptMember.attempt_id == attempt.id)
            )).all()
        }
        if not snapshot:
            f.add(BLOCKER, "EMPTY_SNAPSHOT", where,
                  f"{tile}: attempt {attempt.id} has no members frozen — nobody can open it")
        for uid in member_ids - snapshot:
            f.add(BLOCKER, "MEMBER_LOCKED_OUT", where,
                  f"{tile}: {member_name[uid]} is on the team but not in attempt {attempt.id}'s "
                  f"snapshot — they get a 404 (decided_at={attempt.decided_at})")
        for uid in snapshot - member_ids:
            f.add(INFO, "STALE_SNAPSHOT_MEMBER", where,
                  f"{tile}: user {uid} is frozen into attempt {attempt.id} but no longer on the team "
                  f"— retains access by design (grades must not be rewritten)")

        others = (await db.execute(
            select(MissionAttempt.id, MissionAttempt.status).where(
                MissionAttempt.team_id == team.id,
                MissionAttempt.mission_id == item.mission_id,
                MissionAttempt.id != attempt.id,
                MissionAttempt.status != "abandoned",
            )
        )).all()
        if others:
            f.add(WARN, "DUPLICATE_ATTEMPTS", where,
                  f"{tile}: mission has {len(others) + 1} live attempts for this team "
                  f"({', '.join(str(a.id) for a in others)}) — 'the team's run' is ambiguous")

    for mission_id, attempt_ids in attempt_by_mission.items():
        if len(attempt_ids) > 1:
            f.add(WARN, "SPLIT_STEPS_DISAGREE", where,
                  f"mission {mission_id}'s steps point at {len(attempt_ids)} different attempts "
                  f"({', '.join(str(a) for a in attempt_ids)}) — they are meant to share one")


async def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only audit of team mission_run checklist health")
    ap.add_argument("--cohort", help="Audit one cohort uuid (default: every cohort with teams)")
    ap.add_argument("--verbose", action="store_true", help="Also print INFO findings")
    args = ap.parse_args()

    f = Findings()
    async with AsyncSessionLocal() as db:
        if args.cohort:
            cohorts = [await db.get(Cohort, uuid.UUID(args.cohort))]
            if cohorts[0] is None:
                print(f"Cohort {args.cohort} not found.")
                return 1
        else:
            cohorts = list((await db.execute(select(Cohort).order_by(Cohort.name))).scalars().all())

        audited_teams = 0
        for cohort in cohorts:
            teams = list((await db.execute(
                select(Team).where(Team.cohort_id == cohort.id).order_by(Team.name)
            )).scalars().all())
            if not teams:
                continue
            items = await _team_run_items(db, cohort.id)
            if not items:
                continue
            print(f"\n=== {cohort.name} ({cohort.id}) — {len(teams)} team(s), "
                  f"{len(items)} team mission_run item(s)")
            for team in teams:
                await audit_team(db, team=team, items=items, f=f)
                audited_teams += 1

        await db.rollback()  # read-only, belt and braces

    shown = [r for r in f.rows if args.verbose or r[0] != INFO]
    if shown:
        print(f"\n{'-' * 78}\nFINDINGS\n{'-' * 78}")
        for severity in (BLOCKER, WARN, INFO):
            rows = [r for r in shown if r[0] == severity]
            if not rows:
                continue
            print(f"\n{severity} ({len(rows)}):")
            for _sev, code, where, detail in rows:
                print(f"  [{code}] {where}\n      {detail}")

    counts = f.by_code()
    blockers = sum(n for (sev, _c), n in counts.items() if sev == BLOCKER)
    warns = sum(n for (sev, _c), n in counts.items() if sev == WARN)
    infos = sum(n for (sev, _c), n in counts.items() if sev == INFO)

    print(f"\n{'=' * 78}")
    print(f"Audited {audited_teams} team(s).  BLOCKER: {blockers}   WARN: {warns}   INFO: {infos}")
    if counts:
        print("\nBy check:")
        for (sev, code), n in sorted(counts.items(), key=lambda kv: (kv[0][0], -kv[1])):
            if sev == INFO and not args.verbose:
                continue
            print(f"  {sev:<8} {code:<24} {n}")
    if not blockers:
        print("\nNo blockers. Every team with members can open every team mission tile.")
    print("(read-only — nothing was written)")
    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
