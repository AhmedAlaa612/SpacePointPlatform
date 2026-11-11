"""Checklist item submissions export (.xlsx) — works for both Workshops and
Competitions, and both team-scoped (`one row per team`) and individual-scoped
(`one row per student`) checklist items.

When multiple items are selected, each selected item is exported onto its own
worksheet tab in the returned `.xlsx` workbook, with columns tailored to that
item's specific submission format (single link, single text, labeled multi-link
fields, free-form multi-link, tabular grid config, poster link, quiz score, or
arcade game score).
"""

from __future__ import annotations

import io
import re
import uuid

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lms.arcade_game import ArcadeGameAttempt
from app.models.lms.cohort_quiz import CohortQuizAttempt
from app.models.lms.program import (
    LmsProgram,
    LmsProgramAssignment,
    LmsProgramItem,
    LmsProgramItemProgress,
    LmsProgramTeamItemProgress,
)
from app.models.missions.design import Design
from app.models.missions.mission import MissionAttempt
from app.models.sessions.cohort import Cohort
from app.models.team import Team, TeamMember
from app.models.user import User
from app.services.lms.program import effective_cohort_program_items
from app.services.lms.progress import batch_course_completion

MAX_COLUMN_WIDTH = 60
_INVALID_SHEET_CHARS = re.compile(r"[:\\/?*\[\]]")


def _style_header(sheet: Worksheet) -> None:
    header_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="0F172A")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(vertical="center")
    sheet.row_dimensions[1].height = 24


def _autosize_and_linkify(sheet: Worksheet) -> None:
    link_font = Font(name="Calibri", size=11, color="2563EB", underline="single")
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, str):
                val = cell.value.strip()
                if val.startswith(("http://", "https://")) and "\n" not in val and " " not in val:
                    cell.hyperlink = val
                    cell.font = link_font

    for col_cells in sheet.columns:
        length = max(
            (max((len(line) for line in str(c.value).splitlines()), default=0) for c in col_cells if c.value is not None),
            default=0,
        )
        sheet.column_dimensions[col_cells[0].column_letter].width = min(max(length + 3, 12), MAX_COLUMN_WIDTH)


def _unique_sheet_title(raw_title: str, used_titles: set[str]) -> str:
    cleaned = _INVALID_SHEET_CHARS.sub(" ", (raw_title or "Item")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned) or "Item"
    base = cleaned[:31].rstrip()
    if base.lower() not in {t.lower() for t in used_titles}:
        used_titles.add(base)
        return base
    idx = 2
    while True:
        suffix = f" ({idx})"
        candidate = f"{cleaned[: 31 - len(suffix)].rstrip()}{suffix}"
        if candidate.lower() not in {t.lower() for t in used_titles}:
            used_titles.add(candidate)
            return candidate
        idx += 1


def _fmt_dt(dt) -> str:
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M")


def _infer_table_columns(item: LmsProgramItem, all_submitted_links: list[list[dict]]) -> tuple[str, list[dict]]:
    table_config = item.submission_table_config or {}
    tag_label = table_config.get("tag_label") or "Tag"
    configured_cols = table_config.get("columns") or []
    if configured_cols:
        return tag_label, configured_cols

    col_keys: list[str] = []
    seen_keys: set[str] = set()
    has_any_url = False
    for links in all_submitted_links:
        for entry in links or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("url"):
                has_any_url = True
            vals = entry.get("values")
            if isinstance(vals, dict):
                for k in vals.keys():
                    if k not in seen_keys:
                        seen_keys.add(k)
                        col_keys.append(k)

    cols: list[dict] = []
    if has_any_url and "url" not in seen_keys:
        cols.append({"key": "url", "label": "Link", "type": "link"})
    for k in col_keys:
        cols.append({
            "key": k,
            "label": k.replace("_", " ").title(),
            "type": "link" if ("link" in k.lower() or "url" in k.lower()) else "text",
        })
    return tag_label, cols


def _is_table_item(item: LmsProgramItem, all_submitted_links: list[list[dict]]) -> bool:
    if item.submission_table_config:
        return True
    if not item.submission_multi_link:
        return False
    for links in all_submitted_links:
        for entry in links or []:
            if isinstance(entry, dict) and (entry.get("tag") or (isinstance(entry.get("values"), dict) and len(entry["values"]) > 0)):
                return True
    return False


async def _populate_item_sheet(
    db: AsyncSession,
    *,
    sheet: Worksheet,
    items_by_cohort: list[tuple[Cohort, LmsProgramItem]],
    mode: str,
    include_cohort_col: bool,
) -> None:
    if not items_by_cohort:
        sheet.append(["Notice", "No matching checklist item found."])
        _style_header(sheet)
        _autosize_and_linkify(sheet)
        return

    representative_item = items_by_cohort[0][1]
    cohort_ids = [c.id for c, _ in items_by_cohort]
    cohort_name_by_id = {c.id: c.name for c, _ in items_by_cohort}
    item_by_cohort_id = {c.id: item for c, item in items_by_cohort}
    item_ids = [item.id for _, item in items_by_cohort]

    # Load teams & team members for these cohorts
    team_stmt = select(Team).where(Team.cohort_id.in_(cohort_ids))
    if mode == "participant":
        team_stmt = team_stmt.where(Team.is_observer.is_(False))
    elif mode == "observer":
        team_stmt = team_stmt.where(Team.is_observer.is_(True))
    teams = list((await db.execute(team_stmt.order_by(Team.name))).scalars().all())
    team_ids = [t.id for t in teams]

    members_by_team: dict[uuid.UUID, list[uuid.UUID]] = {tid: [] for tid in team_ids}
    team_by_cohort_user: dict[tuple[uuid.UUID, uuid.UUID], Team] = {}
    team_by_id = {t.id: t for t in teams}
    all_user_ids: set[uuid.UUID] = set()

    if team_ids:
        tm_rows = (await db.execute(
            select(TeamMember.team_id, TeamMember.user_id).where(TeamMember.team_id.in_(team_ids))
        )).all()
        for tid, uid in tm_rows:
            members_by_team[tid].append(uid)
            all_user_ids.add(uid)
            t_obj = team_by_id.get(tid)
            if t_obj and t_obj.cohort_id:
                team_by_cohort_user[(t_obj.cohort_id, uid)] = t_obj

    # Also load all teams for individual student team-name resolution even if mode is mixed
    if representative_item.scope != "team":
        all_cohort_teams = list((await db.execute(
            select(Team).where(Team.cohort_id.in_(cohort_ids))
        )).scalars().all())
        all_ct_ids = [t.id for t in all_cohort_teams]
        all_ct_by_id = {t.id: t for t in all_cohort_teams}
        if all_ct_ids:
            ct_rows = (await db.execute(
                select(TeamMember.team_id, TeamMember.user_id).where(TeamMember.team_id.in_(all_ct_ids))
            )).all()
            for tid, uid in ct_rows:
                t_obj = all_ct_by_id.get(tid)
                if t_obj and t_obj.cohort_id:
                    team_by_cohort_user[(t_obj.cohort_id, uid)] = t_obj

    if representative_item.scope == "team":
        # ── TEAM-SCOPED ITEM: ONE ROW PER TEAM ───────────────────────────
        tp_rows = (await db.execute(
            select(LmsProgramTeamItemProgress).where(
                LmsProgramTeamItemProgress.item_id.in_(item_ids),
                LmsProgramTeamItemProgress.team_id.in_(team_ids),
            )
        )).scalars().all() if team_ids else []
        tp_by_team: dict[uuid.UUID, LmsProgramTeamItemProgress] = {r.team_id: r for r in tp_rows}

        for r in tp_rows:
            if r.updated_by_user_id:
                all_user_ids.add(r.updated_by_user_id)

        users = (await db.execute(select(User).where(User.id.in_(all_user_ids)))).scalars().all() if all_user_ids else []
        users_by_id = {u.id: u for u in users}

        attempt_ids = {r.mission_attempt_id for r in tp_rows if r.mission_attempt_id is not None}
        poster_by_attempt: dict[uuid.UUID, str] = {}
        attempt_status_by_id: dict[uuid.UUID, str] = {}
        if attempt_ids:
            att_rows = (await db.execute(
                select(MissionAttempt.id, MissionAttempt.status).where(MissionAttempt.id.in_(attempt_ids))
            )).all()
            attempt_status_by_id = {aid: st for aid, st in att_rows}
            design_rows = (await db.execute(
                select(Design.attempt_id, Design.poster_url).where(Design.attempt_id.in_(attempt_ids))
            )).all()
            poster_by_attempt = {aid: url for aid, url in design_rows if url}

        all_submitted_links = [
            r.submitted_links for r in tp_rows if isinstance(r.submitted_links, list) and r.submitted_links
        ]
        is_table = _is_table_item(representative_item, all_submitted_links)

        prefix_headers = (["Cohort"] if include_cohort_col else []) + [
            "Team Name",
            "Team ID / Code",
            "Members",
            "Member Emails",
            "Status",
        ]
        suffix_headers = ["Submitted By", "Submitted At"]

        teams_sorted = sorted(
            teams,
            key=lambda t: (
                cohort_name_by_id.get(t.cohort_id, "").lower() if include_cohort_col else "",
                (t.name or "").lower(),
            ),
        )

        if is_table:
            tag_label, table_cols = _infer_table_columns(representative_item, all_submitted_links)
            col_headers = ["Entry #", tag_label, *[c.get("label") or c["key"] for c in table_cols]]
            sheet.append([*prefix_headers, *col_headers, *suffix_headers])

            for team in teams_sorted:
                tp = tp_by_team.get(team.id)
                member_users = sorted(
                    [users_by_id[uid] for uid in members_by_team.get(team.id, []) if uid in users_by_id],
                    key=lambda u: (u.full_name or "").lower(),
                )
                members_str = ", ".join(u.full_name for u in member_users if u.full_name)
                emails_str = ", ".join(u.email for u in member_users if u.email)
                status_val = tp.status if tp else "pending"
                if representative_item.item_type == "team_setup" and status_val == "pending":
                    status_val = "done"
                sub_by = users_by_id[tp.updated_by_user_id].full_name if (tp and tp.updated_by_user_id in users_by_id) else ""
                sub_at = _fmt_dt(tp.updated_at if tp else None)
                row_prefix = ([cohort_name_by_id.get(team.cohort_id, "")] if include_cohort_col else []) + [
                    team.name,
                    team.roster_team_id or team.join_code or "",
                    members_str,
                    emails_str,
                    status_val,
                ]
                row_suffix = [sub_by or "", sub_at]

                links = tp.submitted_links if (tp and isinstance(tp.submitted_links, list)) else []
                if not links:
                    sheet.append([*row_prefix, "", "", *["" for _ in table_cols], *row_suffix])
                else:
                    for idx, entry in enumerate(links, start=1):
                        if not isinstance(entry, dict):
                            continue
                        tag_val = entry.get("tag") or entry.get("label") or ""
                        vals_dict = entry.get("values") if isinstance(entry.get("values"), dict) else {}
                        cells: list[str] = []
                        for col in table_cols:
                            ckey = col["key"]
                            ctype = col.get("type", "text")
                            raw = (entry.get("url") or vals_dict.get(ckey)) if ctype == "link" else vals_dict.get(ckey)
                            cells.append(str(raw) if raw is not None else "")
                        sheet.append([*row_prefix, idx, tag_val, *cells, *row_suffix])

        elif representative_item.submission_multi_link:
            label_specs = representative_item.submission_link_labels or []
            if label_specs:
                label_names: list[str] = [spec["label"] for spec in label_specs if isinstance(spec, dict) and spec.get("label")]
                seen_labels = set(label_names)
                for links in all_submitted_links:
                    for entry in links:
                        if isinstance(entry, dict) and entry.get("label") and entry["label"] not in seen_labels:
                            seen_labels.add(entry["label"])
                            label_names.append(entry["label"])
                sheet.append([*prefix_headers, *label_names, *suffix_headers])

                for team in teams_sorted:
                    tp = tp_by_team.get(team.id)
                    member_users = sorted(
                        [users_by_id[uid] for uid in members_by_team.get(team.id, []) if uid in users_by_id],
                        key=lambda u: (u.full_name or "").lower(),
                    )
                    members_str = ", ".join(u.full_name for u in member_users if u.full_name)
                    emails_str = ", ".join(u.email for u in member_users if u.email)
                    status_val = tp.status if tp else "pending"
                    sub_by = users_by_id[tp.updated_by_user_id].full_name if (tp and tp.updated_by_user_id in users_by_id) else ""
                    sub_at = _fmt_dt(tp.updated_at if tp else None)
                    row_prefix = ([cohort_name_by_id.get(team.cohort_id, "")] if include_cohort_col else []) + [
                        team.name,
                        team.roster_team_id or team.join_code or "",
                        members_str,
                        emails_str,
                        status_val,
                    ]
                    by_label: dict[str, str] = {}
                    for entry in (tp.submitted_links if (tp and isinstance(tp.submitted_links, list)) else []):
                        if isinstance(entry, dict) and entry.get("label"):
                            by_label[entry["label"]] = entry.get("url") or entry.get("text") or ""
                    sheet.append([
                        *row_prefix,
                        *[by_label.get(lbl, "") for lbl in label_names],
                        sub_by or "",
                        sub_at,
                    ])
            else:
                max_links = max((len(links) for links in all_submitted_links), default=1)
                link_headers = [f"Link {i}" for i in range(1, max_links + 1)]
                sheet.append([*prefix_headers, *link_headers, *suffix_headers])

                for team in teams_sorted:
                    tp = tp_by_team.get(team.id)
                    member_users = sorted(
                        [users_by_id[uid] for uid in members_by_team.get(team.id, []) if uid in users_by_id],
                        key=lambda u: (u.full_name or "").lower(),
                    )
                    members_str = ", ".join(u.full_name for u in member_users if u.full_name)
                    emails_str = ", ".join(u.email for u in member_users if u.email)
                    status_val = tp.status if tp else "pending"
                    sub_by = users_by_id[tp.updated_by_user_id].full_name if (tp and tp.updated_by_user_id in users_by_id) else ""
                    sub_at = _fmt_dt(tp.updated_at if tp else None)
                    row_prefix = ([cohort_name_by_id.get(team.cohort_id, "")] if include_cohort_col else []) + [
                        team.name,
                        team.roster_team_id or team.join_code or "",
                        members_str,
                        emails_str,
                        status_val,
                    ]
                    entries = tp.submitted_links if (tp and isinstance(tp.submitted_links, list)) else []
                    cells: list[str] = []
                    for i in range(max_links):
                        if i < len(entries) and isinstance(entries[i], dict):
                            e = entries[i]
                            val = e.get("url") or e.get("text") or ""
                            lbl = e.get("label")
                            cells.append(f"{lbl}: {val}" if lbl and val else val)
                        else:
                            cells.append("")
                    sheet.append([*row_prefix, *cells, sub_by or "", sub_at])

        else:
            is_text = representative_item.item_type == "submission" and representative_item.submission_field_type == "text"
            sub_header = "Submitted Text" if is_text else "Submitted Link"
            sheet.append([*prefix_headers, sub_header, *suffix_headers])

            for team in teams_sorted:
                tp = tp_by_team.get(team.id)
                member_users = sorted(
                    [users_by_id[uid] for uid in members_by_team.get(team.id, []) if uid in users_by_id],
                    key=lambda u: (u.full_name or "").lower(),
                )
                members_str = ", ".join(u.full_name for u in member_users if u.full_name)
                emails_str = ", ".join(u.email for u in member_users if u.email)
                status_val = tp.status if tp else "pending"
                if representative_item.item_type == "team_setup" and status_val == "pending":
                    status_val = "done"
                elif representative_item.item_type == "mission_run" and tp and tp.mission_attempt_id:
                    att_st = attempt_status_by_id.get(tp.mission_attempt_id)
                    if att_st == "passed":
                        status_val = "done"
                sub_by = users_by_id[tp.updated_by_user_id].full_name if (tp and tp.updated_by_user_id in users_by_id) else ""
                sub_at = _fmt_dt((tp.updated_at or tp.completed_at) if tp else None)
                row_prefix = ([cohort_name_by_id.get(team.cohort_id, "")] if include_cohort_col else []) + [
                    team.name,
                    team.roster_team_id or team.join_code or "",
                    members_str,
                    emails_str,
                    status_val,
                ]
                sub_val = ""
                if tp:
                    if is_text:
                        sub_val = tp.submitted_text or tp.submitted_url or ""
                    else:
                        sub_val = tp.submitted_url or tp.submitted_text or ""
                        if not sub_val and representative_item.item_type == "mission_run" and tp.mission_attempt_id:
                            sub_val = poster_by_attempt.get(tp.mission_attempt_id, "")
                sheet.append([*row_prefix, sub_val, sub_by or "", sub_at])

    else:
        # ── INDIVIDUAL-SCOPED ITEM: ONE ROW PER STUDENT ──────────────────
        assign_stmt = select(LmsProgramAssignment).where(LmsProgramAssignment.cohort_id.in_(cohort_ids))
        if mode == "participant":
            assign_stmt = assign_stmt.where(LmsProgramAssignment.mode == "participant")
        elif mode == "observer":
            assign_stmt = assign_stmt.where(LmsProgramAssignment.mode == "observer")
        assignments = list((await db.execute(assign_stmt)).scalars().all())
        assignment_ids = [a.id for a in assignments]
        assign_user_ids = {a.user_id for a in assignments}

        users = (await db.execute(select(User).where(User.id.in_(assign_user_ids)))).scalars().all() if assign_user_ids else []
        users_by_id = {u.id: u for u in users}

        prog_rows = (await db.execute(
            select(LmsProgramItemProgress).where(
                LmsProgramItemProgress.assignment_id.in_(assignment_ids),
                LmsProgramItemProgress.item_id.in_(item_ids),
            )
        )).scalars().all() if assignment_ids else []
        prog_by_assignment: dict[uuid.UUID, LmsProgramItemProgress] = {r.assignment_id: r for r in prog_rows}

        attempt_ids = {r.mission_attempt_id for r in prog_rows if r.mission_attempt_id is not None}
        poster_by_attempt: dict[uuid.UUID, str] = {}
        attempt_status_by_id: dict[uuid.UUID, str] = {}
        if attempt_ids:
            att_rows = (await db.execute(
                select(MissionAttempt.id, MissionAttempt.status).where(MissionAttempt.id.in_(attempt_ids))
            )).all()
            attempt_status_by_id = {aid: st for aid, st in att_rows}
            design_rows = (await db.execute(
                select(Design.attempt_id, Design.poster_url).where(Design.attempt_id.in_(attempt_ids))
            )).all()
            poster_by_attempt = {aid: url for aid, url in design_rows if url}

        # Batch course/quiz/arcade info if needed
        quiz_attempt_by_user_item: dict[tuple[uuid.UUID, uuid.UUID], CohortQuizAttempt] = {}
        if representative_item.item_type == "quiz" and assign_user_ids:
            q_rows = (await db.execute(
                select(CohortQuizAttempt).where(
                    CohortQuizAttempt.program_item_id.in_(item_ids),
                    CohortQuizAttempt.user_id.in_(assign_user_ids),
                )
            )).scalars().all()
            quiz_attempt_by_user_item = {(q.user_id, q.program_item_id): q for q in q_rows}

        arcade_best_by_user: dict[uuid.UUID, int] = {}
        if representative_item.item_type == "arcade_game" and representative_item.arcade_game_id and assign_user_ids:
            ag_rows = (await db.execute(
                select(ArcadeGameAttempt.user_id, func.max(ArcadeGameAttempt.score))
                .where(
                    ArcadeGameAttempt.game_id == representative_item.arcade_game_id,
                    ArcadeGameAttempt.user_id.in_(assign_user_ids),
                )
                .group_by(ArcadeGameAttempt.user_id)
            )).all()
            arcade_best_by_user = {uid: int(sc or 0) for uid, sc in ag_rows}

        course_done_users: set[uuid.UUID] = set()
        if representative_item.item_type == "course" and representative_item.course_id and assign_user_ids:
            comp_map = await batch_course_completion(
                db, user_ids=sorted(assign_user_ids, key=str), course_id=representative_item.course_id,
            )
            for uid, comp in comp_map.items():
                if comp["modules_total"] > 0 and comp["modules_done"] == comp["modules_total"]:
                    course_done_users.add(uid)

        all_submitted_links = [
            r.submitted_links for r in prog_rows if isinstance(r.submitted_links, list) and r.submitted_links
        ]
        is_table = _is_table_item(representative_item, all_submitted_links)

        prefix_headers = (["Cohort"] if include_cohort_col else []) + [
            "Student Name",
            "Email",
            "Team",
            "Status",
        ]
        suffix_headers = ["Submitted At"]

        assignments_sorted = sorted(
            assignments,
            key=lambda a: (
                cohort_name_by_id.get(a.cohort_id, "").lower() if include_cohort_col else "",
                (users_by_id.get(a.user_id).full_name if a.user_id in users_by_id and users_by_id[a.user_id].full_name else "").lower(),
            ),
        )

        def _student_prefix(a: LmsProgramAssignment, p: LmsProgramItemProgress | None) -> tuple[list[str], str]:
            u = users_by_id.get(a.user_id)
            t = team_by_cohort_user.get((a.cohort_id, a.user_id)) if a.cohort_id else None
            c_item = item_by_cohort_id.get(a.cohort_id, representative_item)
            st = p.status if p else "pending"
            if c_item.item_type == "course" and a.user_id in course_done_users:
                st = "done"
            elif c_item.item_type == "quiz":
                qa = quiz_attempt_by_user_item.get((a.user_id, c_item.id))
                if qa and qa.status == "submitted":
                    st = "done"
            elif c_item.item_type == "mission_run" and p and p.mission_attempt_id:
                if attempt_status_by_id.get(p.mission_attempt_id) == "passed":
                    st = "done"
            sub_at = _fmt_dt((p.updated_at or p.completed_at) if p else None)
            row_pref = ([cohort_name_by_id.get(a.cohort_id, "")] if include_cohort_col else []) + [
                u.full_name if u and u.full_name else "",
                u.email if u and u.email else "",
                t.name if t else "",
                st,
            ]
            return row_pref, sub_at

        if is_table:
            tag_label, table_cols = _infer_table_columns(representative_item, all_submitted_links)
            col_headers = ["Entry #", tag_label, *[c.get("label") or c["key"] for c in table_cols]]
            sheet.append([*prefix_headers, *col_headers, *suffix_headers])

            for a in assignments_sorted:
                p = prog_by_assignment.get(a.id)
                row_prefix, sub_at = _student_prefix(a, p)
                links = p.submitted_links if (p and isinstance(p.submitted_links, list)) else []
                if not links:
                    sheet.append([*row_prefix, "", "", *["" for _ in table_cols], sub_at])
                else:
                    for idx, entry in enumerate(links, start=1):
                        if not isinstance(entry, dict):
                            continue
                        tag_val = entry.get("tag") or entry.get("label") or ""
                        vals_dict = entry.get("values") if isinstance(entry.get("values"), dict) else {}
                        cells: list[str] = []
                        for col in table_cols:
                            ckey = col["key"]
                            ctype = col.get("type", "text")
                            raw = (entry.get("url") or vals_dict.get(ckey)) if ctype == "link" else vals_dict.get(ckey)
                            cells.append(str(raw) if raw is not None else "")
                        sheet.append([*row_prefix, idx, tag_val, *cells, sub_at])

        elif representative_item.submission_multi_link:
            label_specs = representative_item.submission_link_labels or []
            if label_specs:
                label_names = [spec["label"] for spec in label_specs if isinstance(spec, dict) and spec.get("label")]
                seen_labels = set(label_names)
                for links in all_submitted_links:
                    for entry in links:
                        if isinstance(entry, dict) and entry.get("label") and entry["label"] not in seen_labels:
                            seen_labels.add(entry["label"])
                            label_names.append(entry["label"])
                sheet.append([*prefix_headers, *label_names, *suffix_headers])

                for a in assignments_sorted:
                    p = prog_by_assignment.get(a.id)
                    row_prefix, sub_at = _student_prefix(a, p)
                    by_label: dict[str, str] = {}
                    for entry in (p.submitted_links if (p and isinstance(p.submitted_links, list)) else []):
                        if isinstance(entry, dict) and entry.get("label"):
                            by_label[entry["label"]] = entry.get("url") or entry.get("text") or ""
                    sheet.append([*row_prefix, *[by_label.get(lbl, "") for lbl in label_names], sub_at])
            else:
                max_links = max((len(links) for links in all_submitted_links), default=1)
                link_headers = [f"Link {i}" for i in range(1, max_links + 1)]
                sheet.append([*prefix_headers, *link_headers, *suffix_headers])

                for a in assignments_sorted:
                    p = prog_by_assignment.get(a.id)
                    row_prefix, sub_at = _student_prefix(a, p)
                    entries = p.submitted_links if (p and isinstance(p.submitted_links, list)) else []
                    cells = []
                    for i in range(max_links):
                        if i < len(entries) and isinstance(entries[i], dict):
                            e = entries[i]
                            val = e.get("url") or e.get("text") or ""
                            lbl = e.get("label")
                            cells.append(f"{lbl}: {val}" if lbl and val else val)
                        else:
                            cells.append("")
                    sheet.append([*row_prefix, *cells, sub_at])

        elif representative_item.item_type == "quiz":
            sheet.append([*prefix_headers, "Score", "Total", "Percentage", *suffix_headers])
            for a in assignments_sorted:
                p = prog_by_assignment.get(a.id)
                c_item = item_by_cohort_id.get(a.cohort_id, representative_item)
                row_prefix, sub_at = _student_prefix(a, p)
                qa = quiz_attempt_by_user_item.get((a.user_id, c_item.id))
                score_val: int | str = ""
                total_val: int | str = ""
                pct_val = ""
                if qa and qa.status == "submitted":
                    score_val = qa.score if qa.score is not None else 0
                    total_val = qa.total if qa.total is not None else 0
                    pct_val = f"{round(100 * int(score_val) / int(total_val))}%" if total_val else "0%"
                    if not sub_at and qa.submitted_at:
                        sub_at = _fmt_dt(qa.submitted_at)
                sheet.append([*row_prefix, score_val, total_val, pct_val, sub_at])

        elif representative_item.item_type == "arcade_game":
            sheet.append([*prefix_headers, "Best Score", *suffix_headers])
            for a in assignments_sorted:
                p = prog_by_assignment.get(a.id)
                row_prefix, sub_at = _student_prefix(a, p)
                best = arcade_best_by_user.get(a.user_id, "")
                sheet.append([*row_prefix, best, sub_at])

        else:
            is_text = representative_item.item_type == "submission" and representative_item.submission_field_type == "text"
            sub_header = "Submitted Text" if is_text else "Submitted Link"
            sheet.append([*prefix_headers, sub_header, *suffix_headers])

            for a in assignments_sorted:
                p = prog_by_assignment.get(a.id)
                row_prefix, sub_at = _student_prefix(a, p)
                sub_val = ""
                if p:
                    if is_text:
                        sub_val = p.submitted_text or p.submitted_url or ""
                    else:
                        sub_val = p.submitted_url or p.submitted_text or ""
                        if not sub_val and representative_item.item_type == "mission_run" and p.mission_attempt_id:
                            sub_val = poster_by_attempt.get(p.mission_attempt_id, "")
                sheet.append([*row_prefix, sub_val, sub_at])

    _style_header(sheet)
    _autosize_and_linkify(sheet)


async def export_cohort_items_submissions_workbook(
    db: AsyncSession,
    *,
    cohort_id: uuid.UUID,
    item_ids: list[uuid.UUID] | None = None,
    mode: str = "participant",
) -> bytes:
    """Exports one worksheet per selected checklist item for a cohort."""
    cohort = await db.get(Cohort, cohort_id)
    resolved = await effective_cohort_program_items(db, cohort_id)
    items = list(resolved[1]) if (cohort and resolved is not None) else []

    if item_ids:
        wanted = set(item_ids)
        selected_items = [i for i in items if i.id in wanted]
    else:
        # Default to submission-bearing items if no explicit item_ids passed, or all items if none
        selected_items = [
            i for i in items
            if i.item_type == "submission" or (i.item_type == "mission_run" and i.mission_step_key == "poster")
        ] or items

    wb = openpyxl.Workbook()
    if not cohort or not selected_items:
        sheet = wb.active
        sheet.title = "Submissions"
        sheet.append(["Notice", "No matching checklist items found for this cohort."])
        _style_header(sheet)
        _autosize_and_linkify(sheet)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    used_titles: set[str] = set()
    for idx, item in enumerate(selected_items):
        title = _unique_sheet_title(item.title, used_titles)
        if idx == 0:
            sheet = wb.active
            sheet.title = title
        else:
            sheet = wb.create_sheet(title)
        await _populate_item_sheet(
            db,
            sheet=sheet,
            items_by_cohort=[(cohort, item)],
            mode=mode,
            include_cohort_col=False,
        )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def export_program_items_submissions_workbook(
    db: AsyncSession,
    *,
    lms_program_id: uuid.UUID,
    item_ids: list[uuid.UUID] | None = None,
    restrict_to_cohort_ids: set[uuid.UUID] | None = None,
    mode: str = "participant",
) -> bytes:
    """Program-wide sibling — exports one worksheet per selected program item
    across all cohorts using this LMS program (matching cohort-override items
    by id or `(title, item_type, scope)`)."""
    program = await db.get(LmsProgram, lms_program_id)
    wb = openpyxl.Workbook()
    if program is None or program.program_id is None:
        sheet = wb.active
        sheet.title = "Submissions"
        sheet.append(["Notice", "Program not found."])
        _style_header(sheet)
        _autosize_and_linkify(sheet)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    program_items = list((await db.execute(
        select(LmsProgramItem)
        .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == program.id)
        .order_by(LmsProgramItem.position)
    )).scalars().all())

    if item_ids:
        wanted = set(item_ids)
        selected_program_items = [i for i in program_items if i.id in wanted]
    else:
        selected_program_items = [
            i for i in program_items
            if i.item_type == "submission" or (i.item_type == "mission_run" and i.mission_step_key == "poster")
        ] or program_items

    cohort_stmt = select(Cohort).where(Cohort.program_id == program.program_id).order_by(Cohort.name)
    if restrict_to_cohort_ids is not None:
        if not restrict_to_cohort_ids:
            cohorts = []
        else:
            cohort_stmt = cohort_stmt.where(Cohort.id.in_(restrict_to_cohort_ids))
            cohorts = list((await db.execute(cohort_stmt)).scalars().all())
    else:
        cohorts = list((await db.execute(cohort_stmt)).scalars().all())

    if not cohorts or not selected_program_items:
        sheet = wb.active
        sheet.title = "Submissions"
        sheet.append(["Notice", "No cohorts or checklist items found for this program."])
        _style_header(sheet)
        _autosize_and_linkify(sheet)
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    cohort_effective: dict[uuid.UUID, list[LmsProgramItem]] = {}
    for c in cohorts:
        res = await effective_cohort_program_items(db, c.id)
        if res is not None:
            cohort_effective[c.id] = list(res[1])

    used_titles: set[str] = set()
    for idx, p_item in enumerate(selected_program_items):
        title = _unique_sheet_title(p_item.title, used_titles)
        if idx == 0:
            sheet = wb.active
            sheet.title = title
        else:
            sheet = wb.create_sheet(title)

        matched_pairs: list[tuple[Cohort, LmsProgramItem]] = []
        for c in cohorts:
            c_items = cohort_effective.get(c.id, [])
            match = next((ci for ci in c_items if ci.id == p_item.id), None)
            if match is None:
                match = next(
                    (ci for ci in c_items if ci.title == p_item.title and ci.item_type == p_item.item_type and ci.scope == p_item.scope),
                    None,
                )
            if match is not None:
                matched_pairs.append((c, match))

        await _populate_item_sheet(
            db,
            sheet=sheet,
            items_by_cohort=matched_pairs,
            mode=mode,
            include_cohort_col=True,
        )

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
