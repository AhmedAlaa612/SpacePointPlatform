"""Competition registration import (2026-08-24, preview/confirm added
2026-08-28) — bulk-create teams from a Google Form export (Excel/CSV).
Registration/filtering itself stays in Google Forms per the boss thread; the
platform's job starts once ops has a final roster to import.

Two phases now, not one: `preview_registration_sheet` parses the file and
reports per-row issues (missing fields, a malformed email) **without writing
anything** — ops reviews it, optionally fixes what's flagged in the browser,
then calls `import_registrations` with the (possibly still-flagged) rows to
commit. This replaced a one-pass immediately-committed design after a shifted
spreadsheet column put a non-email value straight into a real account's
`email` column undetected (2026-08-28) — a competition roster is ops-curated
but not ops-*verified* per cell, and nothing caught it until the admin user
list itself broke on the bad row (fixed separately: `UserOut` no longer
re-validates `email` on the way out). No contact-merge review queue still;
`services/sessions/importer.py`'s general importer is the one that needs that,
this one's rosters stay small enough that ops fixing a flagged row by hand in
the preview is the whole review step.

A malformed email is a *warning*, not a blocker: `_blocking_issues` (missing
team/member/email) is the only thing `_import_row` actually refuses to
write — ops can knowingly import a row with a bad address (no working email
for that student yet) rather than being forced to invent one to get past
the preview. Nothing downstream chokes on it: the admin list reads `email`
as a plain string, and the set-password email send below is best-effort and
swallows its own failures.

Reuses the same identity/registration/LMS primitives the desk and the bulk
importer already use (`resolve_or_create_contact`, `register`,
`sync_registration_lms`) rather than hand-rolling account creation again —
a competition participant is a normal student account with a normal
Registration, nothing competition-specific about either.

Team grouping (2026-09-14 rewrite): the sheet's `team_id` — an external
code from ops's own roster system — is now the grouping key, not
`team_name`. A row's `team_name` is optional: if present it's used as the
team's real display name outright; if blank, the team is created with
`name` seeded to `team_id` as a literal placeholder, and students set
their own real name later (deadline-gated `team_setup` checklist item —
see `services/lms/program.py`). Re-importing the same sheet never
overwrites a name a team has already set for real (its own rename, or an
ops fix) — only ever applies the sheet's name while the team is still at
its own placeholder. See `app/models/team.py`'s module docstring for the
full `roster_team_id`/`name` shape this relies on.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import asdict, dataclass
from typing import Literal

import openpyxl
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sessions.cohort import Cohort
from app.models.sessions.registration import Registration
from app.models.team import Team
from app.models.user import User
from app.services.competitions.team_management import rename_team
from app.services.lms.ops_integration import sync_registration_lms
from app.services.sessions.registration import register
from app.services.spine.identity import resolve_or_create_contact
from app.services.teams import create_team, join_team, team_member_ids

REQUIRED_COLUMNS = ["team_id", "member_name", "email"]
OPTIONAL_COLUMNS = ["phone", "nationality", "team_name", "school"]

# Deliberately loose — this only needs to catch "a column shifted and this
# clearly isn't an email" (a bare number, a name, empty), not reject every
# edge case a real RFC 5322 address could take. That's the same bar the
# admin-side incident this whole preview step exists for was: `email='456'`,
# not something borderline.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Ops's actual selection tracker (the sheet the roster gets exported from —
# "Eligible" for the qualifier cohort, "Final Selection" for the finalist
# one) uses these column labels, not the canonical names above. Aliased
# here rather than renaming the canonical keys, since those also read as
# `row.get("member_name")`/`row.get("school")` in `_import_row` below and
# match the general bulk importer's convention. "Team Name" already matches
# `team_name` natively and needs no alias.
_HEADER_ALIASES = {
    "student_name": "member_name",
    "school_/_university": "school",
    "school_university": "school",  # in case a re-save strips the slash
}


@dataclass
class ImportRowResult:
    row_number: int
    team_id: str | None
    team_name: str | None
    email: str | None
    disposition: Literal["created", "matched", "error"]
    reason: str | None = None
    registration_id: uuid.UUID | None = None


@dataclass
class ImportPreviewRow:
    """One parsed sheet row, before anything is written — every field ops
    can edit in the browser, plus what's wrong with it so far (empty when
    the row is clean). `issues` is advisory here; `import_registrations`
    re-runs the identical check and actually refuses to commit a row that
    still has one, so a client skipping the preview step can't smuggle a
    bad row through."""
    row_number: int
    team_id: str | None
    team_name: str | None
    member_name: str | None
    email: str | None
    phone: str | None
    nationality: str | None
    school: str | None
    issues: list[str]


def _normalize_header(raw: object) -> str:
    slug = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _HEADER_ALIASES.get(slug, slug)


def _rows_from_csv(file_bytes: bytes) -> list[list]:
    # utf-8-sig eats the BOM Excel/Sheets stamp on a CSV export — without
    # it the first header cell decodes as "﻿team_name" and silently
    # never matches "team_name", which looks identical to a missing column.
    text = file_bytes.decode("utf-8-sig", errors="replace")
    return list(csv.reader(io.StringIO(text)))


def _rows_from_xlsx(file_bytes: bytes) -> list[list]:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as exc:
        # openpyxl raises whatever the zip/xml layer underneath happens to
        # raise on garbage input (BadZipFile, KeyError, its own
        # InvalidFileException...) — none of that is useful to ops, who
        # just picked the wrong file or exported it wrong.
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Couldn't read this file as an Excel spreadsheet. Upload a real .xlsx, or a .csv export.",
        ) from exc
    sheet = wb.worksheets[0]
    return [[c.value for c in sheet[row_idx]] for row_idx in range(1, sheet.max_row + 1)]


# Ops's actual tracker sheets ("Eligible", "Final Selection") each open with
# a title row and a stage-description row before the real header — same
# "title row / banner row above the header" shape
# services/sessions/importer.py's general bulk importer already tolerates.
# 10 rows is generous headroom over the tracker's real 2.
_MAX_HEADER_SCAN_ROWS = 10


def _find_header_row(rows: list[list]) -> tuple[int, dict[str, int]]:
    """Scans the first `_MAX_HEADER_SCAN_ROWS` rows for one whose normalized
    cells cover every required column, same idiom as
    `services/sessions/importer.py::_find_header_row`."""
    for row_idx, cells in enumerate(rows[:_MAX_HEADER_SCAN_ROWS]):
        header = [_normalize_header(c) for c in cells]
        col_index = {name: i for i, name in enumerate(header) if name}
        if all(c in col_index for c in REQUIRED_COLUMNS):
            return row_idx, col_index
    raise HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=f"Couldn't find a header row with all required columns ({', '.join(REQUIRED_COLUMNS)}) "
               f"in the first {_MAX_HEADER_SCAN_ROWS} rows",
    )


def parse_registration_sheet(file_bytes: bytes, filename: str | None = None) -> list[dict]:
    """One dict per data row. Tolerates a title row and/or a stage-description
    row above the real header (scans the first `_MAX_HEADER_SCAN_ROWS` rows
    for it) — ops's actual tracker sheets open with exactly that shape.
    Accepts .xlsx or .csv — the upload widget advertises both, and ops's
    tracker gets exported as either depending on how the sheet is
    downloaded."""
    is_csv = (filename or "").lower().endswith(".csv")
    all_rows = _rows_from_csv(file_bytes) if is_csv else _rows_from_xlsx(file_bytes)
    header_idx, col_index = _find_header_row(all_rows)

    rows = []
    for offset, cells in enumerate(all_rows[header_idx + 1:]):
        row_number = header_idx + offset + 2  # 1-indexed sheet row number
        if all(c is None or str(c).strip() == "" for c in cells):
            continue
        # CSV rows (and a ragged xlsx row) can be shorter than the header —
        # cells past the end read as None rather than indexing off the end.
        row = {name: (cells[idx] if idx < len(cells) else None) for name, idx in col_index.items()}
        rows.append({"row_number": row_number, "raw": row})
    return rows


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


@dataclass
class CleanedRow:
    row_number: int
    team_id: str | None
    team_name: str | None
    member_name: str | None
    email: str | None
    phone: str | None
    nationality: str | None
    school: str | None


def _clean_row(row_number: int, raw: dict) -> CleanedRow:
    return CleanedRow(
        row_number=row_number,
        team_id=_clean_str(raw.get("team_id")),
        team_name=_clean_str(raw.get("team_name")),
        member_name=_clean_str(raw.get("member_name")),
        email=_clean_str(raw.get("email")),
        phone=_clean_str(raw.get("phone")),
        nationality=_clean_str(raw.get("nationality")),
        school=_clean_str(raw.get("school")),
    )


def _blocking_issues(row: CleanedRow) -> list[str]:
    """Missing data the import can't proceed without at all — these are the
    only issues that stop `_import_row` from writing a row. `team_name` is
    NOT here — it's optional (see module docstring): a blank one just means
    this team hasn't been named yet, not a bad row."""
    issues = []
    if not row.team_id:
        issues.append("Team ID is required")
    if not row.member_name:
        issues.append("Member name is required")
    if not row.email:
        issues.append("Email is required")
    return issues


def _row_issues(row: CleanedRow) -> list[str]:
    """Every note worth showing ops for this row — the blocking ones above,
    plus a malformed-but-present email, which is a *warning* rather than a
    blocker: ops sometimes knowingly imports a row with a bad email (no
    working address for that student yet, fix it later) and confirm must
    still let that through rather than silently dropping the row. A bad
    address never crashes anything downstream — the admin list reads
    `email` as a plain string (not re-validated), and the set-password
    email send is best-effort and swallows its own failures. Preview shows
    every issue at once, not just the first, so ops doesn't fix-and-reupload
    one problem at a time."""
    issues = _blocking_issues(row)
    if row.email and not _EMAIL_RE.match(row.email):
        issues.append("Email is not valid")
    return issues


def preview_registration_sheet(file_bytes: bytes, filename: str | None = None) -> list[ImportPreviewRow]:
    """Parse the sheet and report every row's issues — no database access at
    all, so calling this as many times as ops needs while fixing flagged
    cells in the browser is always safe. `import_registrations` (further
    down) is the only function that actually writes anything."""
    parsed = parse_registration_sheet(file_bytes, filename)
    out = []
    for entry in parsed:
        row = _clean_row(entry["row_number"], entry["raw"])
        out.append(ImportPreviewRow(
            row_number=row.row_number, team_id=row.team_id, team_name=row.team_name, member_name=row.member_name,
            email=row.email, phone=row.phone, nationality=row.nationality, school=row.school,
            issues=_row_issues(row),
        ))
    return out


async def _import_row(
    db: AsyncSession, *, row_number: int, raw: dict, cohort: Cohort, send_welcome_email: bool = True,
) -> ImportRowResult:
    row = _clean_row(row_number, raw)
    issues = _blocking_issues(row)
    if issues:
        return ImportRowResult(row_number, row.team_id, row.team_name, row.email, "error", "; ".join(issues))
    team_id, team_name, member_name, email, phone, nationality, school = (
        row.team_id, row.team_name, row.member_name, row.email, row.phone, row.nationality, row.school,
    )

    contact, _evaluation = await resolve_or_create_contact(
        db, full_name=member_name, phone=phone, email=email, contact_roles=["student"],
        role_event_source="import", organization_name=school, nationality=nationality,
    )

    existing_reg = (await db.execute(
        select(Registration).where(Registration.contact_id == contact.id, Registration.cohort_id == cohort.id)
    )).scalars().first()
    is_new_registration = existing_reg is None
    if existing_reg is None:
        try:
            registration = await register(
                db, contact_id=contact.id, cohort_id=cohort.id, registered_via="import", payment_status="waived",
            )
        except HTTPException as exc:
            return ImportRowResult(row_number, team_id, team_name, email, "error", exc.detail)
    else:
        registration = existing_reg

    user = await sync_registration_lms(
        db, registration=registration, cohort=cohort, create_account=True,
        send_welcome_email=send_welcome_email,
    )
    if user is None:
        # The email already belongs to an existing User not linked to this
        # contact (e.g. a pre-existing LMS account).  That's fine — look them
        # up by email and still add them to the team; the registration was
        # already created above, so they have a seat in this cohort either way.
        user = (await db.execute(
            select(User).where(User.email == email)
        )).scalars().first()
        if user is None:
            return ImportRowResult(
                row_number, team_id, team_name, email, "error",
                "Registered, but couldn't create a student account (email may already belong to a different account)",
            )

    # Grouped by the sheet's team_id now, never by name — see module
    # docstring. A team not found for this (cohort, team_id) yet is a brand
    # new one; `name` falls back to `team_id` itself when the sheet has no
    # name for it, which is also exactly how "still unnamed" is detected
    # elsewhere (Team.name == Team.roster_team_id).
    team = (await db.execute(
        select(Team).where(Team.cohort_id == cohort.id, Team.roster_team_id == team_id)
    )).scalars().first()
    try:
        if team is None:
            team = await create_team(
                db, name=team_name or team_id, created_by=user.id, cohort_id=cohort.id, member_ids=[user.id],
                roster_team_id=team_id,
            )
        else:
            if user.id not in await team_member_ids(db, team_id=team.id):
                await join_team(db, team_id=team.id, user_id=user.id)
            # Only apply the sheet's name while the team is still at its own
            # placeholder — never clobber a name a team already set for
            # real (their own rename, or an ops fix), even on a re-import.
            if team_name and team.name == team.roster_team_id:
                await rename_team(db, team_id=team.id, name=team_name)
    except HTTPException as exc:
        # A name collision (this row's team_name, or the team_id-as-
        # placeholder-name, matching another team's real name
        # case-insensitively) — flag the row rather than aborting the
        # whole batch; the registration/account above already committed
        # to the session either way.
        return ImportRowResult(row_number, team_id, team_name, email, "error", exc.detail)

    return ImportRowResult(
        row_number, team_id, team.name, email, "created" if is_new_registration else "matched",
        registration_id=registration.id,
    )


async def import_registrations(
    db: AsyncSession, *, cohort_id: uuid.UUID, rows: list[dict], send_welcome_email: bool = True,
) -> list[ImportRowResult]:
    """`rows` is the output of `parse_registration_sheet` (or hand-built the
    same shape) — `[{"row_number": int, "raw": {team_name, member_name,
    email, phone?, school?}}]`. Idempotent on `(contact, cohort)`: re-running
    the exact same sheet twice reports every row `matched`, not duplicated.

    `send_welcome_email` applies to the whole batch — every account created
    (not linked to an existing one) either gets the "Your SpacePoint
    learning account" email or doesn't; there's no per-row control, same as
    the ticket-email decision the router makes for this batch."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    results = []
    for entry in rows:
        result = await _import_row(
            db, row_number=entry["row_number"], raw=entry["raw"], cohort=cohort,
            send_welcome_email=send_welcome_email,
        )
        results.append(result)
    return results


def summarize(results: list[ImportRowResult]) -> dict:
    summary = {"total": len(results), "created": 0, "matched": 0, "error": 0}
    for r in results:
        summary[r.disposition] += 1
    return summary


def results_as_dicts(results: list[ImportRowResult]) -> list[dict]:
    return [asdict(r) for r in results]


def preview_rows_as_dicts(rows: list[ImportPreviewRow]) -> list[dict]:
    return [asdict(r) for r in rows]
