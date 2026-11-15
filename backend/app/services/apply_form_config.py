"""Configurable application form fields, required validation, and answer snapshots.

Provides per-role standard field visibility/requiredness stored in PortalSetting
(under ``apply_field_config_{role}``), validation & question-label snapshotting on
submission, and helper functions to resolve stored answers for admin review
even after questions are edited or soft-deleted.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.apply_config import CONFIGURABLE_APPLY_ROLES, RESERVED_ANSWER_KEYS
from app.models.application_question import ApplicationQuestion
from app.services.settings import get_portal_setting, set_portal_setting


def _f(
    key: str,
    label: str,
    *,
    enabled: bool = True,
    required: bool = False,
    locked: bool = False,
    section: str = "Profile",
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "enabled": enabled,
        "required": required,
        "locked": locked,
        "section": section,
    }


def _public_core_fields(*, invite_required: bool = False) -> list[dict[str, Any]]:
    return [
        _f("full_name", "Full Name", required=True, locked=True, section="Account"),
        _f("email", "Email Address", required=True, locked=True, section="Account"),
        _f("password", "Password", required=True, locked=True, section="Account"),
        _f("phone", "Phone Number", required=False, section="Contact"),
        _f("birthdate", "Date of Birth", required=False, section="Profile"),
        _f("country", "Country", required=True, section="Location"),
        _f("city", "City", required=True, section="Location"),
        _f("invite_code", "Invite / Referral Code", required=invite_required, section="Referral"),
        _f("cv", "CV / Resume Upload", required=True, section="Documents"),
    ]


DEFAULT_ROLE_FIELDS: dict[str, list[dict[str, Any]]] = {
    "ambassador": _public_core_fields(invite_required=False),
    "teacher": _public_core_fields(invite_required=True),
    "facilitator": _public_core_fields(invite_required=False),
    "intern": _public_core_fields(invite_required=False)
    + [
        _f("nationality", "Nationality", required=True, section="Profile"),
        _f("university", "University / Institution", required=False, section="Academic"),
        _f("major", "Major / Field of Study", required=False, section="Academic"),
        _f("university_id_number", "University ID Number", required=False, section="Internship"),
        _f("preferred_city_id", "Preferred Training City", required=False, section="Internship"),
        _f("requested_start_date", "Preferred Start Date", required=False, section="Internship"),
        _f("requested_duration_weeks", "Requested Duration (Weeks)", required=False, section="Internship"),
    ],
    "instructor": [
        _f("full_name", "Full Name", required=True, locked=True, section="Account"),
        _f("email", "Email Address", required=True, locked=True, section="Account"),
        _f("password", "Password", required=True, locked=True, section="Account"),
        _f("phone", "Phone Number", required=True, section="Contact"),
        _f("birthdate", "Date of Birth", required=True, section="Profile"),
        _f("nationality", "Nationality", required=True, section="Profile"),
        _f("work_status", "Work Status", required=True, section="Profile"),
        _f("fluent_languages", "Fluent Languages", required=True, section="Profile"),
        _f("graduated_university", "Graduated From University", required=True, section="Academic"),
        _f("university", "Other / Unlisted University", required=False, section="Academic"),
        _f("highest_degree", "Highest Degree", required=True, section="Academic"),
        _f("country", "Country of Residence", required=True, section="Location"),
        _f("city_of_residence_id", "City of Residence", required=True, section="Location"),
        _f("deliver_city_ids", "Delivery Cities", required=True, section="Teaching"),
        _f("background_areas", "Background Areas", required=True, section="Teaching"),
        _f("has_own_transportation", "Has Own Transportation", required=False, section="Logistics"),
        _f("invite_code", "Invite / Referral Code", required=False, section="Referral"),
        _f("cv", "CV / Resume Upload", required=False, section="Documents"),
    ],
    "organization": [
        _f("org_name_latin", "Organization Name (English)", required=True, locked=True, section="Organization"),
        _f("org_name_arabic", "Organization Name (Arabic)", required=False, section="Organization"),
        _f("org_type", "Organization Type", required=True, section="Organization"),
        _f("country", "Country", required=True, section="Location"),
        _f("city", "City", required=False, section="Location"),
        _f("full_name", "Contact Person Name", required=True, locked=True, section="Contact"),
        _f("email", "Work Email", required=True, locked=True, section="Account"),
        _f("phone", "Phone Number", required=True, section="Contact"),
        _f("password", "Password", required=True, locked=True, section="Account"),
    ],
    "student": [
        _f("full_name", "Full Name", required=True, locked=True, section="Account"),
        _f("email", "Email", required=True, locked=True, section="Account"),
        _f("password", "Password", required=True, locked=True, section="Account"),
        _f("phone", "Phone Number", required=True, section="Contact"),
        _f("nationality", "Nationality", required=True, section="Profile"),
        _f("date_of_birth", "Date of Birth", required=False, section="Profile"),
        _f("country", "Country", required=False, section="Location"),
        _f("city", "City", required=False, section="Location"),
        _f("invite_code", "Invite / Referral Code", required=False, section="Referral"),
        _f("parent_info", "Parent / Guardian Details", required=False, section="Guardian"),
    ],
}


def _config_key(role: str) -> str:
    return f"apply_field_config_{role}"


def _custom_answers_key(user_id: uuid.UUID | str) -> str:
    return f"applicant_custom_answers_{user_id}"


def _validate_role(role: str) -> None:
    if role not in CONFIGURABLE_APPLY_ROLES:
        raise HTTPException(status_code=404, detail=f"Unknown application role: {role}")


async def _read_role_config_blob(db: AsyncSession, role: str) -> dict[str, Any]:
    raw = await get_portal_setting(db, _config_key(role), default="")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


async def get_hidden_question_ids(db: AsyncSession, role: str) -> set[str]:
    parsed = await _read_role_config_blob(db, role)
    return {str(x) for x in (parsed.get("hidden_question_ids") or []) if x}


async def set_question_visibility(db: AsyncSession, role: str, qid: str, enabled: bool) -> None:
    _validate_role(role)
    parsed = await _read_role_config_blob(db, role)
    hidden_ids = {str(x) for x in (parsed.get("hidden_question_ids") or []) if x}
    if enabled:
        hidden_ids.discard(str(qid))
    else:
        hidden_ids.add(str(qid))
    payload = json.dumps({
        "has_custom_override": bool(parsed.get("has_custom_override", False)),
        "fields": parsed.get("fields") or [],
        "hidden_question_ids": sorted(hidden_ids),
    })
    await set_portal_setting(db, _config_key(role), payload)


async def get_role_form_config(db: AsyncSession, role: str) -> dict[str, Any]:
    """Return merged standard-field config + active custom questions for a role."""
    _validate_role(role)
    defaults = DEFAULT_ROLE_FIELDS[role]
    parsed = await _read_role_config_blob(db, role)
    saved_by_key: dict[str, dict[str, Any]] = {}
    has_custom_override = False
    if parsed:
        has_custom_override = bool(parsed.get("has_custom_override", True))
        for item in parsed.get("fields", []):
            if isinstance(item, dict) and item.get("key"):
                saved_by_key[item["key"]] = item
    hidden_ids = {str(x) for x in (parsed.get("hidden_question_ids") or []) if x}

    merged_fields: list[dict[str, Any]] = []
    for base in defaults:
        override = saved_by_key.get(base["key"])
        if base["locked"]:
            merged_fields.append(dict(base))
            continue
        enabled = bool(override.get("enabled", base["enabled"])) if override else base["enabled"]
        required = bool(override.get("required", base["required"])) if override else base["required"]
        if not enabled:
            required = False
        merged_fields.append(
            {
                **base,
                "enabled": enabled,
                "required": required,
            }
        )

    questions = (
        await db.execute(
            select(ApplicationQuestion)
            .where(ApplicationQuestion.audience == role, ApplicationQuestion.is_active.is_(True))
            .order_by(ApplicationQuestion.sort_order, ApplicationQuestion.created_at)
        )
    ).scalars().all()

    return {
        "role": role,
        "has_custom_override": has_custom_override,
        "fields": merged_fields,
        "questions": [
            {
                "id": str(q.id),
                "question_text": q.question_text,
                "question_type": q.question_type,
                "required": q.required,
                "enabled": str(q.id) not in hidden_ids,
                "order": q.sort_order,
                "options": q.options or [],
            }
            for q in questions
        ],
    }


async def set_role_form_config(
    db: AsyncSession,
    role: str,
    fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """Persist admin toggles for built-in fields of a role."""
    _validate_role(role)
    defaults = {item["key"]: item for item in DEFAULT_ROLE_FIELDS[role]}
    incoming_by_key = {item["key"]: item for item in fields if isinstance(item, dict) and item.get("key") in defaults}

    sanitized: list[dict[str, Any]] = []
    for base in DEFAULT_ROLE_FIELDS[role]:
        inc = incoming_by_key.get(base["key"])
        if base["locked"]:
            sanitized.append({"key": base["key"], "enabled": True, "required": True})
            continue
        enabled = bool(inc.get("enabled", base["enabled"])) if inc else base["enabled"]
        required = bool(inc.get("required", base["required"])) if inc else base["required"]
        if not enabled:
            required = False
        sanitized.append({"key": base["key"], "enabled": enabled, "required": required})

    existing = await _read_role_config_blob(db, role)
    hidden_ids = sorted({str(x) for x in (existing.get("hidden_question_ids") or []) if x})
    payload = json.dumps({
        "has_custom_override": True,
        "fields": sanitized,
        "hidden_question_ids": hidden_ids,
    })
    await set_portal_setting(db, _config_key(role), payload)
    await db.commit()
    return await get_role_form_config(db, role)


def is_value_present(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return True
    if isinstance(val, str):
        return bool(val.strip())
    if isinstance(val, (list, dict, tuple, set)):
        return len(val) > 0
    return True


def enforce_standard_field_requirements(
    config: dict[str, Any],
    values: dict[str, Any],
) -> None:
    """Validate required built-in fields when admin has customized role field settings."""
    if not config.get("has_custom_override"):
        return
    missing: list[str] = []
    for field in config.get("fields", []):
        if field.get("locked") or not field.get("enabled") or not field.get("required"):
            continue
        key = field["key"]
        if key not in values:
            continue
        if not is_value_present(values[key]):
            missing.append(field["label"])
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required field(s): {', '.join(missing)}",
        )


async def validate_and_snapshot_custom_questions(
    db: AsyncSession,
    role: str,
    raw_answers: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Validate active required custom questions and snapshot question labels at submit time.

    Returns ``(clean_answers, snapshot_map)``.
    """
    _validate_role(role)
    answers = dict(raw_answers) if isinstance(raw_answers, dict) else {}

    active_questions = (
        await db.execute(
            select(ApplicationQuestion)
            .where(ApplicationQuestion.audience == role, ApplicationQuestion.is_active.is_(True))
            .order_by(ApplicationQuestion.sort_order, ApplicationQuestion.created_at)
        )
    ).scalars().all()

    missing: list[str] = []
    snapshots: dict[str, dict[str, Any]] = {}
    existing_snaps = answers.get("_question_snapshots")
    if isinstance(existing_snaps, dict):
        snapshots.update(existing_snaps)

    hidden_ids = await get_hidden_question_ids(db, role)
    for q in active_questions:
        qid = str(q.id)
        if qid in hidden_ids:
            continue
        val = answers.get(qid)
        if q.required and not is_value_present(val):
            missing.append(q.question_text)
        if qid in answers or q.required:
            snapshots[qid] = {
                "question_text": q.question_text,
                "question_type": q.question_type,
                "options": q.options or [],
                "required": q.required,
                "order": q.sort_order,
            }

    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Please answer all required question(s): {'; '.join(missing)}",
        )

    return answers, snapshots


async def resolve_answers_with_questions(
    db: AsyncSession,
    raw_answers: dict[str, Any] | None,
    audience: str | None = None,
) -> list[dict[str, Any]]:
    """Resolve stored answers into human-readable question/answer pairs.

    Prefers stored ``_question_snapshots`` so edits/deletions never erase what the
    applicant saw, and falls back to ALL DB questions (including ``is_active=False``)
    so raw UUIDs are never shown to admins.
    """
    if not isinstance(raw_answers, dict) or not raw_answers:
        return []

    # Support nested RoleRequest.details shape where custom answers live in details["answers"]
    candidate_answers: dict[str, Any] = {}
    snapshots: dict[str, dict[str, Any]] = {}
    if isinstance(raw_answers.get("_question_snapshots"), dict):
        snapshots.update(raw_answers["_question_snapshots"])
    if isinstance(raw_answers.get("answers"), dict):
        nested = raw_answers["answers"]
        if isinstance(nested.get("_question_snapshots"), dict):
            snapshots.update(nested["_question_snapshots"])
        for k, v in nested.items():
            if k not in RESERVED_ANSWER_KEYS:
                candidate_answers[k] = v

    for k, v in raw_answers.items():
        if k not in RESERVED_ANSWER_KEYS:
            candidate_answers[k] = v

    if not candidate_answers:
        return []

    # Collect UUID keys to fetch from apply_questions regardless of is_active / audience
    uuid_keys: list[uuid.UUID] = []
    for k in candidate_answers:
        try:
            uuid_keys.append(uuid.UUID(str(k)))
        except ValueError:
            pass

    q_by_id: dict[str, ApplicationQuestion] = {}
    if uuid_keys:
        rows = (
            await db.execute(select(ApplicationQuestion).where(ApplicationQuestion.id.in_(uuid_keys)))
        ).scalars().all()
        q_by_id = {str(q.id): q for q in rows}
    elif audience:
        rows = (
            await db.execute(select(ApplicationQuestion).where(ApplicationQuestion.audience == audience))
        ).scalars().all()
        q_by_id = {str(q.id): q for q in rows}

    resolved: list[dict[str, Any]] = []
    for raw_key, value in candidate_answers.items():
        key_str = str(raw_key)
        snap = snapshots.get(key_str) or {}
        q = q_by_id.get(key_str)
        is_uuid_key = False
        try:
            uuid.UUID(key_str)
            is_uuid_key = True
        except ValueError:
            pass

        if snap or q:
            label = snap.get("question_text") or (q.question_text if q else f"Removed Question ({key_str[:8]})")
            q_type = snap.get("question_type") or (q.question_type if q else "text")
            is_deleted = bool(q is None or not q.is_active) if is_uuid_key else False
            sort_order = snap.get("order", q.sort_order if q else 9999)
            is_legacy = False
        elif is_uuid_key:
            label = f"Removed Question ({key_str[:8]})"
            q_type = "text"
            is_deleted = True
            sort_order = 9999
            is_legacy = False
        else:
            if key_str.endswith("_id") or key_str.startswith("_"):
                continue
            label = key_str.replace("_", " ").strip().title()
            q_type = "text"
            is_deleted = False
            sort_order = 9998
            is_legacy = True

        resolved.append(
            {
                "key": key_str,
                "label": label,
                "question_type": q_type,
                "value": value,
                "is_deleted": is_deleted,
                "is_legacy": is_legacy,
                "_sort": sort_order,
            }
        )

    resolved.sort(key=lambda item: (item["_sort"], item["label"]))
    for item in resolved:
        item.pop("_sort", None)
    return resolved


async def save_user_custom_answers(
    db: AsyncSession,
    user_id: uuid.UUID,
    answers: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
) -> None:
    """Persist custom answers for direct User-based applications (instructor / organization)."""
    payload = {k: v for k, v in answers.items() if k not in RESERVED_ANSWER_KEYS}
    if snapshots:
        payload["_question_snapshots"] = snapshots
    if not payload:
        return
    await set_portal_setting(db, _custom_answers_key(user_id), json.dumps(payload))


async def get_user_custom_answers(
    db: AsyncSession,
    user_id: uuid.UUID,
    audience: str | None = None,
) -> list[dict[str, Any]]:
    raw = await get_portal_setting(db, _custom_answers_key(user_id), default="")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return await resolve_answers_with_questions(db, parsed, audience=audience)
