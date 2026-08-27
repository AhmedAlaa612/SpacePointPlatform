"""Competition registration import (2026-08-24) — bulk-create teams from a
Google Form export (Excel/CSV). Registration/filtering itself stays in
Google Forms per the boss thread; the platform's job starts once ops has a
final roster to import.

Deliberately lighter than `services/sessions/importer.py`'s general sheet
importer: no dry-run/`ImportBatch` two-phase flow, no contact-merge review
queue — a competition roster is small (tens of rows, not hundreds), already
hand-curated by ops before it gets here, and re-running the exact same sheet
twice should just match instead of duplicating. One pass, immediately
committed, is the right amount of machinery for that.

Reuses the same identity/registration/LMS primitives the desk and the bulk
importer already use (`resolve_or_create_contact`, `register`,
`sync_registration_lms`) rather than hand-rolling account creation again —
a competition participant is a normal student account with a normal
Registration, nothing competition-specific about either.
"""

from __future__ import annotations

import csv
import io
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
from app.services.lms.ops_integration import sync_registration_lms
from app.services.sessions.registration import register
from app.services.spine.identity import resolve_or_create_contact
from app.services.teams import create_team, join_team, team_member_ids

REQUIRED_COLUMNS = ["team_name", "member_name", "email"]
OPTIONAL_COLUMNS = ["phone", "school"]

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
    team_name: str | None
    email: str | None
    disposition: Literal["created", "matched", "error"]
    reason: str | None = None


def _normalize_header(raw: object) -> str:
    slug = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    return _HEADER_ALIASES.get(slug, slug)


def _rows_from_csv(file_bytes: bytes) -> tuple[list[str], list[list]]:
    # utf-8-sig eats the BOM Excel/Sheets stamp on a CSV export — without
    # it the first header cell decodes as "﻿team_name" and silently
    # never matches "team_name", which looks identical to a missing column.
    text = file_bytes.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return [], []
    return [_normalize_header(c) for c in rows[0]], rows[1:]


def _rows_from_xlsx(file_bytes: bytes) -> tuple[list[str], list[list]]:
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
    header = [_normalize_header(c.value) for c in sheet[1]]
    data_rows = [[c.value for c in sheet[row_idx]] for row_idx in range(2, sheet.max_row + 1)]
    return header, data_rows


def parse_registration_sheet(file_bytes: bytes, filename: str | None = None) -> list[dict]:
    """One dict per data row (header on row 1, exactly — ops controls this
    sheet's format via a shared template, unlike the general bulk importer's
    tolerance for stray title rows above the header). Accepts .xlsx or
    .csv — the upload widget advertises both, and ops's tracker gets
    exported as either depending on how the sheet is downloaded."""
    is_csv = (filename or "").lower().endswith(".csv")
    header, data_rows = _rows_from_csv(file_bytes) if is_csv else _rows_from_xlsx(file_bytes)

    col_index = {name: i for i, name in enumerate(header) if name}
    missing = [c for c in REQUIRED_COLUMNS if c not in col_index]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required column(s): {', '.join(missing)}",
        )

    rows = []
    for offset, cells in enumerate(data_rows):
        row_number = offset + 2
        if all(c is None or str(c).strip() == "" for c in cells):
            continue
        # CSV rows can be shorter than the header (a trailing blank cell is
        # just omitted by whatever exported it) — cells past the end read
        # as None rather than indexing off the end of the row.
        row = {name: (cells[idx] if idx < len(cells) else None) for name, idx in col_index.items()}
        rows.append({"row_number": row_number, "raw": row})
    return rows


def _clean_str(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


async def _import_row(db: AsyncSession, *, row_number: int, raw: dict, cohort: Cohort) -> ImportRowResult:
    team_name = _clean_str(raw.get("team_name"))
    member_name = _clean_str(raw.get("member_name"))
    email = _clean_str(raw.get("email"))
    phone = _clean_str(raw.get("phone"))
    school = _clean_str(raw.get("school"))

    if not team_name:
        return ImportRowResult(row_number, team_name, email, "error", "team_name is required")
    if not member_name:
        return ImportRowResult(row_number, team_name, email, "error", "member_name is required")
    if not email:
        return ImportRowResult(row_number, team_name, email, "error", "email is required")

    contact, _evaluation = await resolve_or_create_contact(
        db, full_name=member_name, phone=phone, email=email, contact_roles=["student"],
        role_event_source="import", organization_name=school,
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
            return ImportRowResult(row_number, team_name, email, "error", exc.detail)
    else:
        registration = existing_reg

    user = await sync_registration_lms(db, registration=registration, cohort=cohort, create_account=True)
    if user is None:
        return ImportRowResult(
            row_number, team_name, email, "error",
            "Registered, but couldn't create a student account (email may already belong to a different account)",
        )

    team = (await db.execute(
        select(Team).where(Team.cohort_id == cohort.id, Team.name == team_name)
    )).scalars().first()
    if team is None:
        team = await create_team(db, name=team_name, created_by=user.id, cohort_id=cohort.id, member_ids=[user.id])
    elif user.id not in await team_member_ids(db, team_id=team.id):
        await join_team(db, team_id=team.id, user_id=user.id)

    return ImportRowResult(row_number, team_name, email, "created" if is_new_registration else "matched")


async def import_registrations(
    db: AsyncSession, *, cohort_id: uuid.UUID, rows: list[dict],
) -> list[ImportRowResult]:
    """`rows` is the output of `parse_registration_sheet` (or hand-built the
    same shape) — `[{"row_number": int, "raw": {team_name, member_name,
    email, phone?, school?}}]`. Idempotent on `(contact, cohort)`: re-running
    the exact same sheet twice reports every row `matched`, not duplicated."""
    cohort = await db.get(Cohort, cohort_id)
    if cohort is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Cohort not found")

    results = []
    for entry in rows:
        result = await _import_row(db, row_number=entry["row_number"], raw=entry["raw"], cohort=cohort)
        results.append(result)
    return results


def summarize(results: list[ImportRowResult]) -> dict:
    summary = {"total": len(results), "created": 0, "matched": 0, "error": 0}
    for r in results:
        summary[r.disposition] += 1
    return summary


def results_as_dicts(results: list[ImportRowResult]) -> list[dict]:
    return [asdict(r) for r in results]
