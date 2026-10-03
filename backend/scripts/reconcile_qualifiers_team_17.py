"""Reconcile and merge duplicated competition teams in a cohort.

Specifically built for Ru'ya Qualifiers cohort (d651bca0-394f-4b47-9fa9-ddea274a430f),
where Team 17 and Team MIRAGE-X were duplicated. Judging scores were uploaded to Team 17,
while students submitted deliverables under Team MIRAGE-X.

This script:
1. Inspects both teams (members, submissions, scores, locks, qualification).
2. Moves competition_scores from Source (Team 17) to Target (MIRAGE-X).
3. Moves missing learner_team_members from Source to Target.
4. Moves missing lms_program_team_item_progress from Source to Target (preserving Target submissions).
5. Moves any mission_attempts from Source to Target.
6. Transfers qualification, timing adjustments, and ops criterion scores to Target.
7. Sets Target roster_team_id = "17".
8. Deletes the redundant Source team.
9. Runs leaderboard verification and scans the cohort for other duplicates.

Usage:
  # Dry-run preview (safe, changes rolled back):
  docker exec spacepoint-api python scripts/reconcile_qualifiers_team_17.py --dry-run

  # Apply changes to the live database:
  docker exec spacepoint-api python scripts/reconcile_qualifiers_team_17.py --commit
"""
import argparse
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import delete, func, select, update
from app.db.session import AsyncSessionLocal
from app.models.competitions.judging import CompetitionScore
from app.models.lms.program import LmsProgramItem, LmsProgramTeamItemProgress
from app.models.missions.mission import MissionAttempt
from app.models.sessions.cohort import Cohort
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.competitions.judging import leaderboard

DEFAULT_COHORT_ID = "d651bca0-394f-4b47-9fa9-ddea274a430f"


async def inspect_team(db, team: Team) -> dict:
    """Fetch all associated records for a team."""
    # Members
    members_res = (await db.execute(
        select(TeamMember, User)
        .join(User, User.id == TeamMember.user_id)
        .where(TeamMember.team_id == team.id)
    )).all()
    members = [{"id": u.id, "name": u.full_name, "email": u.email} for _, u in members_res]

    # Submissions / Progress
    progress_res = (await db.execute(
        select(LmsProgramTeamItemProgress, LmsProgramItem)
        .join(LmsProgramItem, LmsProgramItem.id == LmsProgramTeamItemProgress.item_id)
        .where(LmsProgramTeamItemProgress.team_id == team.id)
    )).all()
    submissions = [
        {
            "progress_id": p.id,
            "item_id": p.item_id,
            "title": item.title,
            "status": p.status,
            "url": p.submitted_url,
            "text": p.submitted_text,
            "links": p.submitted_links,
            "completed_at": p.completed_at,
            "updated_at": p.updated_at,
        }
        for p, item in progress_res
    ]

    # Competition Scores
    scores_res = (await db.execute(
        select(CompetitionScore, User)
        .join(User, User.id == CompetitionScore.judge_user_id)
        .where(CompetitionScore.team_id == team.id)
    )).all()
    scores = [
        {
            "score_id": s.id,
            "rubric_id": s.rubric_id,
            "judge_user_id": s.judge_user_id,
            "judge_name": u.full_name,
            "judge_email": u.email,
            "total_points": s.total_points,
            "bonus_points": s.bonus_points,
            "timing_adjustment": s.timing_adjustment,
            "submitted": s.submitted,
            "criterion_scores": s.criterion_scores,
            "notes": s.notes,
        }
        for s, u in scores_res
    ]

    # Mission Attempts
    attempts_res = (await db.execute(
        select(MissionAttempt).where(MissionAttempt.team_id == team.id)
    )).scalars().all()
    attempts = [
        {"id": a.id, "mission_id": a.mission_id, "attempt_no": a.attempt_no, "status": a.status}
        for a in attempts_res
    ]

    return {
        "team": team,
        "members": members,
        "submissions": submissions,
        "scores": scores,
        "attempts": attempts,
    }


def print_team_card(title: str, data: dict):
    team: Team = data["team"]
    print("=" * 80)
    print(f"📌 {title}: '{team.name}' (UUID: {team.id})")
    print("=" * 80)
    print(f"  Roster Team ID    : {team.roster_team_id}")
    print(f"  Qualification     : {team.qualification}")
    print(f"  Locked At         : {team.final_locked_at} (First: {team.first_locked_at})")
    print(f"  Timing Override   : {team.timing_adjustment_override} (Notes: {team.timing_adjustment_notes})")
    print(f"  Ops Scored At     : {team.ops_scored_at}")
    print(f"  Ops Criteria      : {team.ops_criterion_scores}")
    print(f"  Members ({len(data['members'])})       :")
    for m in data["members"]:
        print(f"    - {m['name']} ({m['email']}) [ID: {m['id']}]")
    if not data["members"]:
        print("    (No members)")

    print(f"  Submissions ({len(data['submissions'])})   :")
    for s in data["submissions"]:
        url_preview = s['url'] or (f"text: {s['text'][:30]}..." if s['text'] else "no link/text")
        print(f"    - [{s['status']}] {s['title']}: {url_preview}")
    if not data["submissions"]:
        print("    (No submissions)")

    print(f"  Scores ({len(data['scores'])})        :")
    for sc in data["scores"]:
        print(f"    - {sc['judge_name']} ({sc['judge_email']}): {sc['total_points']} pts (submitted: {sc['submitted']})")
    if not data["scores"]:
        print("    (No scores)")

    print(f"  Mission Attempts  : {len(data['attempts'])}")
    print()


async def reconcile_cohort_teams(cohort_id: uuid.UUID, commit: bool, source_id_arg=None, target_id_arg=None):
    mode_str = "🚀 COMMIT MODE (Changes will be written to DB)" if commit else "🔍 DRY-RUN MODE (No changes will be saved)"
    print(f"\n{'=' * 80}")
    print(f"Starting Team Reconciliation for Cohort: {cohort_id}")
    print(f"Mode: {mode_str}")
    print(f"{'=' * 80}\n")

    async with AsyncSessionLocal() as db:
        cohort = await db.get(Cohort, cohort_id)
        if not cohort:
            print(f"❌ Error: Cohort '{cohort_id}' not found.")
            return

        print(f"✓ Found Cohort: '{cohort.name}' (Program ID: {cohort.program_id})\n")

        all_teams = (await db.execute(
            select(Team).where(Team.cohort_id == cohort_id)
        )).scalars().all()
        print(f"✓ Total teams in cohort: {len(all_teams)}")

        # 1. Identify Source (17) and Target (MIRAGE-X)
        source_team = None
        target_team = None

        if source_id_arg and target_id_arg:
            source_team = next((t for t in all_teams if str(t.id) == source_id_arg), None)
            target_team = next((t for t in all_teams if str(t.id) == target_id_arg), None)
        else:
            for t in all_teams:
                name_clean = t.name.strip().lower()
                r_id = str(t.roster_team_id).strip().lower() if t.roster_team_id else ""
                
                # Check for Team 17
                if name_clean in ("17", "team 17") or (r_id == "17" and "mirage" not in name_clean):
                    if source_team is None:
                        source_team = t
                
                # Check for MIRAGE-X
                if "mirage" in name_clean:
                    if target_team is None:
                        target_team = t

        if not source_team or not target_team:
            print(f"❌ Could not automatically identify both teams!")
            print(f"   Source (17) found: {'YES - ' + source_team.name if source_team else 'NO'}")
            print(f"   Target (MIRAGE-X) found: {'YES - ' + target_team.name if target_team else 'NO'}")
            print("\nListing all teams in cohort for inspection:")
            for t in all_teams:
                print(f"  - {t.name:30} | roster_id: {str(t.roster_team_id):10} | UUID: {t.id}")
            return

        if source_team.id == target_team.id:
            print(f"❌ Error: Source and Target resolved to the same team ({source_team.id})!")
            return

        # 2. Inspect both teams
        source_data = await inspect_team(db, source_team)
        target_data = await inspect_team(db, target_team)

        print_team_card("SOURCE TEAM (To be merged and removed)", source_data)
        print_team_card("TARGET TEAM (Canonical MIRAGE-X to keep)", target_data)

        # 3. Plan merge operations
        print("=" * 80)
        print("🛠️  PLANNED MERGE ACTIONS:")
        print("=" * 80)

        # A. Scores
        scores_to_move = []
        scores_to_update = []
        for sc in source_data["scores"]:
            matching_target_sc = next(
                (tsc for tsc in target_data["scores"] if tsc["rubric_id"] == sc["rubric_id"] and tsc["judge_user_id"] == sc["judge_user_id"]),
                None
            )
            if not matching_target_sc:
                scores_to_move.append(sc)
            else:
                scores_to_update.append((sc, matching_target_sc))

        print(f"1. Scores:")
        print(f"   - {len(scores_to_move)} score(s) will be transferred directly to Target.")
        for sc in scores_to_move:
            print(f"     * {sc['judge_name']}: {sc['total_points']} pts")
        if scores_to_update:
            print(f"   - {len(scores_to_update)} score(s) already exist on Target and will be reconciled.")

        # B. Members
        target_user_ids = {m["id"] for m in target_data["members"]}
        members_to_move = [m for m in source_data["members"] if m["id"] not in target_user_ids]
        members_redundant = [m for m in source_data["members"] if m["id"] in target_user_ids]
        print(f"2. Members:")
        print(f"   - {len(members_to_move)} member(s) will be transferred to Target.")
        for m in members_to_move:
            print(f"     * {m['name']} ({m['email']})")
        if members_redundant:
            print(f"   - {len(members_redundant)} member(s) already on Target (Source membership row removed).")

        # C. Submissions
        target_item_ids = {s["item_id"] for s in target_data["submissions"]}
        submissions_to_move = [s for s in source_data["submissions"] if s["item_id"] not in target_item_ids]
        submissions_kept_on_target = [s for s in source_data["submissions"] if s["item_id"] in target_item_ids]
        print(f"3. Submissions:")
        print(f"   - Target currently has {len(target_data['submissions'])} submission(s) (WILL BE PRESERVED).")
        if submissions_to_move:
            print(f"   - {len(submissions_to_move)} submission(s) exist only on Source and will be transferred to Target:")
            for s in submissions_to_move:
                print(f"     * {s['title']}: {s['url']}")
        if submissions_kept_on_target:
            print(f"   - {len(submissions_kept_on_target)} duplicate submission row(s) on Source will be dropped in favor of Target's.")

        # D. Mission Attempts
        attempts_to_move = len(source_data["attempts"])
        print(f"4. Mission Attempts:")
        print(f"   - {attempts_to_move} attempt(s) will be transferred.")

        # E. Team Metadata
        print(f"5. Metadata & Attributes:")
        print(f"   - Target name will remain: '{target_team.name}'")
        print(f"   - Target roster_team_id will be set to: '17'")
        if source_team.qualification and not target_team.qualification:
            print(f"   - Qualification '{source_team.qualification}' will be copied to Target.")
        if source_team.timing_adjustment_override is not None and target_team.timing_adjustment_override is None:
            print(f"   - Timing adjustment override ({source_team.timing_adjustment_override}) will be copied to Target.")
        if source_team.ops_criterion_scores and not target_team.ops_criterion_scores:
            print(f"   - Ops criteria scores will be copied to Target.")

        print(f"6. Cleanup:")
        print(f"   - Source team '{source_team.name}' (UUID: {source_team.id}) will be deleted.\n")

        # 4. Execute Reconciliation
        print("=" * 80)
        print("⚙️  EXECUTING RECONCILIATION:")
        print("=" * 80)

        # Move Scores
        for sc in scores_to_move:
            score_obj = await db.get(CompetitionScore, sc["score_id"])
            if score_obj:
                score_obj.team_id = target_team.id
        for sc_src, sc_tgt in scores_to_update:
            src_score_obj = await db.get(CompetitionScore, sc_src["score_id"])
            tgt_score_obj = await db.get(CompetitionScore, sc_tgt["score_id"])
            if src_score_obj and tgt_score_obj:
                if (not tgt_score_obj.submitted or tgt_score_obj.total_points == 0) and src_score_obj.submitted:
                    tgt_score_obj.criterion_scores = src_score_obj.criterion_scores
                    tgt_score_obj.criterion_comments = src_score_obj.criterion_comments
                    tgt_score_obj.bonus_points = src_score_obj.bonus_points
                    tgt_score_obj.timing_adjustment = src_score_obj.timing_adjustment
                    tgt_score_obj.total_points = src_score_obj.total_points
                    tgt_score_obj.notes = src_score_obj.notes
                    tgt_score_obj.submitted = src_score_obj.submitted
                    tgt_score_obj.submitted_at = src_score_obj.submitted_at
                await db.delete(src_score_obj)

        # Move Members
        for m in members_to_move:
            member_obj = await db.scalar(
                select(TeamMember).where(TeamMember.team_id == source_team.id, TeamMember.user_id == m["id"])
            )
            if member_obj:
                member_obj.team_id = target_team.id
        for m in members_redundant:
            member_obj = await db.scalar(
                select(TeamMember).where(TeamMember.team_id == source_team.id, TeamMember.user_id == m["id"])
            )
            if member_obj:
                await db.delete(member_obj)

        # Move Submissions
        for s in submissions_to_move:
            prog_obj = await db.get(LmsProgramTeamItemProgress, s["progress_id"])
            if prog_obj:
                prog_obj.team_id = target_team.id
        for s in submissions_kept_on_target:
            prog_obj = await db.get(LmsProgramTeamItemProgress, s["progress_id"])
            if prog_obj:
                await db.delete(prog_obj)

        # Move Mission Attempts
        await db.execute(
            update(MissionAttempt)
            .where(MissionAttempt.team_id == source_team.id)
            .values(team_id=target_team.id)
        )

        # Metadata reconciliation
        if source_team.qualification and not target_team.qualification:
            target_team.qualification = source_team.qualification
        if source_team.timing_adjustment_override is not None and target_team.timing_adjustment_override is None:
            target_team.timing_adjustment_override = source_team.timing_adjustment_override
            target_team.timing_adjustment_notes = source_team.timing_adjustment_notes
        if source_team.ops_criterion_scores and not target_team.ops_criterion_scores:
            target_team.ops_criterion_scores = source_team.ops_criterion_scores
            target_team.ops_criterion_notes = source_team.ops_criterion_notes
            target_team.ops_scored_by = source_team.ops_scored_by
            target_team.ops_scored_at = source_team.ops_scored_at
        if source_team.final_locked_at and not target_team.final_locked_at:
            target_team.final_locked_at = source_team.final_locked_at
            target_team.final_locked_by = source_team.final_locked_by
        if source_team.first_locked_at and (not target_team.first_locked_at or source_team.first_locked_at < target_team.first_locked_at):
            target_team.first_locked_at = source_team.first_locked_at

        # Clear roster_team_id on source before setting it on target
        source_team.roster_team_id = None
        await db.flush()

        target_team.roster_team_id = "17"

        # Delete source team
        await db.delete(source_team)
        await db.flush()

        print("✓ Database operations staged successfully.")

        # 5. Verify Target Team & Leaderboard
        updated_target_data = await inspect_team(db, target_team)
        print_team_card("VERIFIED CANONICAL TEAM (Post-Merge)", updated_target_data)

        # Check leaderboard
        lb_rows = await leaderboard(db, cohort_id=cohort_id)
        mirage_lb = next((r for r in lb_rows if r["team_id"] == target_team.id), None)
        if mirage_lb:
            print("=" * 80)
            print(f"📊 LEADERBOARD STANDING FOR '{target_team.name}':")
            print("=" * 80)
            print(f"  Rank               : #{mirage_lb['rank']}")
            print(f"  Final Score        : {mirage_lb['score']}")
            print(f"  Normalized Pct     : {mirage_lb['score_percent']}%")
            print(f"  Judges Scored      : {mirage_lb['judges_scored']}")
            print(f"  Qualification      : {mirage_lb['qualification']}")
            print(f"  Timing Adjustment  : {mirage_lb['timing_adjustment']} (Badge: {mirage_lb['timing_badge']})")
            print(f"  Status             : {mirage_lb['status']}")
            for js in mirage_lb["judge_scores"]:
                print(f"    - {js['judge_name']}: {js['total_points']} pts")
            print()

        # 6. Check for any other suspicious duplicate teams in this cohort
        print("=" * 80)
        print("🔍 SCANNING COHORT FOR OTHER POTENTIAL DUPLICATES:")
        print("=" * 80)
        remaining_teams = (await db.execute(
            select(Team).where(Team.cohort_id == cohort_id, Team.id != source_team.id)
        )).scalars().all()

        name_counts = {}
        roster_id_counts = {}
        for t in remaining_teams:
            c_name = t.name.strip().lower()
            name_counts.setdefault(c_name, []).append(t)
            if t.roster_team_id:
                r_id = str(t.roster_team_id).strip().lower()
                roster_id_counts.setdefault(r_id, []).append(t)

        duplicate_found = False
        for name, t_list in name_counts.items():
            if len(t_list) > 1:
                duplicate_found = True
                print(f"  ⚠️ Duplicate Team Name '{name}': {len(t_list)} teams")
                for dt in t_list:
                    print(f"     * ID: {dt.id}, roster_id: {dt.roster_team_id}")

        for r_id, t_list in roster_id_counts.items():
            if len(t_list) > 1:
                duplicate_found = True
                print(f"  ⚠️ Duplicate Roster Team ID '{r_id}': {len(t_list)} teams")
                for dt in t_list:
                    print(f"     * ID: {dt.id}, name: {dt.name}")

        if not duplicate_found:
            print("  ✓ No duplicate team names or duplicate roster IDs found among remaining teams.")
        print()

        # 7. Commit or Rollback
        if commit:
            await db.commit()
            print("🎉 SUCCESS! All changes have been committed to the production database.")
            print(f"Team '{target_team.name}' now holds all scores, submissions, and roster ID 17.")
            print("Redundant team '17' has been safely removed.\n")
        else:
            await db.rollback()
            print("🔒 DRY-RUN COMPLETE: Transaction rolled back. No changes were committed.")
            print("To apply these changes, re-run with --commit.")


def main():
    parser = argparse.ArgumentParser(description="Reconcile and merge duplicated competition teams in a cohort.")
    parser.add_argument("--cohort-id", default=DEFAULT_COHORT_ID, help="Target cohort UUID")
    parser.add_argument("--source-team", help="Explicit source team UUID (the one to merge from and remove)")
    parser.add_argument("--target-team", help="Explicit target team UUID (the canonical team to keep)")
    parser.add_argument("--commit", action="store_true", help="Commit changes to database (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without committing (default)")
    args = parser.parse_args()

    cohort_uuid = uuid.UUID(args.cohort_id)
    asyncio.run(reconcile_cohort_teams(
        cohort_id=cohort_uuid,
        commit=args.commit,
        source_id_arg=args.source_team,
        target_id_arg=args.target_team,
    ))


if __name__ == "__main__":
    main()
