"""Hybrid-live resolver for Program Event Landing Pages (WebsiteEvent) and
Program/Multi-Cohort Case Studies (WebsiteCaseStudy).

Live fields are resolved from the portal DB on read and merged with editor
overrides using the precedence:
    1. overrides[field] (explicit editor override)
    2. live[field]      (calculated live from portal DB)
    3. stored[field]    (fallback editorial column on the row)

Public reads use a short 60-second in-process TTL cache; admin/editor reads
always bypass the cache so editors see instant updates.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory.city import City
from app.models.inventory.location import Location
from app.models.lms.program import LmsProgram, LmsProgramItem
from app.models.sessions.cohort import Cohort
from app.models.sessions.program import Program
from app.models.sessions.registration import Registration
from app.models.sessions.session import Session
from app.models.spine.contact import Contact
from app.models.spine.organization import Organization
from app.models.team import Team
from app.models.website_case_study import WebsiteCaseStudy
from app.models.website_event import WebsiteEvent
from app.services.sessions.registration import ACTIVE_REGISTRATION_STATUSES

_CACHE_TTL_SECONDS = 60.0
_event_live_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cs_live_cache: dict[str, tuple[float, dict[str, Any]]] = {}

PROGRAM_TO_EVENT_TYPE = {
    "competition": "competition",
    "workshop": "workshop",
    "course": "workshop",
    "info_session": "talk",
}

PROGRAM_TO_CS_CATEGORY = {
    "competition": "Challenges & Competitions",
    "course": "National Programs",
    "workshop": "Roadshows",
    "info_session": "Universities",
}

EVENT_LIVE_FIELDS: tuple[str, ...] = (
    "title",
    "about_text",
    "event_type",
    "host_org_name",
    "date_label",
    "city",
    "location",
    "partners",
    "curriculum_chapters",
    "steps",
)

CASE_STUDY_LIVE_FIELDS: tuple[str, ...] = (
    "title",
    "subtitle",
    "category",
    "card_summary",
    "overview_text",
    "partner_name",
    "partners",
    "metrics",
    "card_metrics",
    "curriculum_chapters",
    "structure_sections",
)


def invalidate_program_web_cache(program_id: UUID | str | None = None) -> None:
    if program_id is None:
        _event_live_cache.clear()
        _cs_live_cache.clear()
        return
    key = str(program_id)
    _event_live_cache.pop(key, None)
    _cs_live_cache.clear()


def _format_date_short(d: date | None) -> str | None:
    if not d:
        return None
    return d.strftime("%b %d, %Y")


def _format_date_span(starts: date | None, ends: date | None) -> str | None:
    if starts and ends and starts != ends:
        return f"{_format_date_short(starts)} – {_format_date_short(ends)}"
    if starts:
        return _format_date_short(starts)
    if ends:
        return _format_date_short(ends)
    return None


async def _fetch_lms_curriculum(db: AsyncSession, program_id: UUID) -> list[dict[str, Any]]:
    lms_prog = (
        await db.execute(select(LmsProgram).where(LmsProgram.program_id == program_id))
    ).scalars().first()
    if not lms_prog:
        return []
    items = (
        await db.execute(
            select(LmsProgramItem)
            .where(LmsProgramItem.owner_type == "program", LmsProgramItem.owner_id == lms_prog.id)
            .order_by(LmsProgramItem.position)
        )
    ).scalars().all()
    return [
        {
            "chapter_num": f"Ch. {idx + 1}",
            "title": it.title,
            "icon": "check" if it.item_type == "checkpoint" else "sat",
        }
        for idx, it in enumerate(items[:12])
    ]


async def resolve_program_event_live(
    db: AsyncSession,
    program_id: UUID,
    *,
    use_cache: bool = False,
) -> dict[str, Any]:
    """Compute live landing-page data for a Program (no pricing fields)."""
    cache_key = str(program_id)
    if use_cache:
        hit = _event_live_cache.get(cache_key)
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_SECONDS:
            return hit[1]

    program = await db.get(Program, program_id)
    if not program:
        return {
            "title": "",
            "about_text": None,
            "event_type": "workshop",
            "host_org_name": "SpacePoint",
            "partners": [],
            "date_label": None,
            "city": None,
            "location": None,
            "curriculum_chapters": [],
            "steps": [],
        }

    # Host / Partner
    host_org_name = "SpacePoint"
    partners: list[dict[str, Any]] = []
    if program.organization_id:
        org = await db.get(Organization, program.organization_id)
        if org:
            host_org_name = org.name_latin or org.name_arabic or "Partner Organization"
            partners.append({"name": host_org_name, "role": "Host Organization", "logo_url": ""})

    # Eligible cohorts for this program (exclude draft, cancelled, [Template])
    # Crucial: on SpacePoint-owned programs, exclude partner-run cohorts
    stmt = select(Cohort).where(
        Cohort.program_id == program.id,
        Cohort.status.notin_(["draft", "cancelled"]),
        ~Cohort.name.ilike("[Template]%"),
        func.lower(func.trim(Cohort.name)) != "template",
    )
    if program.organization_id is None:
        stmt = stmt.where(Cohort.organization_id.is_(None))
    stmt = stmt.order_by(Cohort.starts_on.asc().nullslast(), Cohort.created_at.asc())
    cohorts = (await db.execute(stmt)).scalars().all()

    cohort_ids = [c.id for c in cohorts]
    loc_ids = [c.location_id for c in cohorts if c.location_id]

    loc_map: dict[UUID, tuple[str, str | None]] = {}
    if loc_ids:
        rows = (
            await db.execute(
                select(Location.id, Location.name, City.name)
                .outerjoin(City, Location.city_id == City.id)
                .where(Location.id.in_(loc_ids))
            )
        ).all()
        for lid, lname, cname in rows:
            loc_map[lid] = (lname, cname)

    reg_counts: dict[UUID, int] = {}
    sess_counts: dict[UUID, int] = {}
    if cohort_ids:
        for cid, cnt in (
            await db.execute(
                select(Registration.cohort_id, func.count(Registration.id))
                .where(
                    Registration.cohort_id.in_(cohort_ids),
                    Registration.status.in_(ACTIVE_REGISTRATION_STATUSES),
                )
                .group_by(Registration.cohort_id)
            )
        ).all():
            reg_counts[cid] = int(cnt or 0)

        for cid, cnt in (
            await db.execute(
                select(Session.cohort_id, func.count(Session.id))
                .where(Session.cohort_id.in_(cohort_ids))
                .group_by(Session.cohort_id)
            )
        ).all():
            sess_counts[cid] = int(cnt or 0)

    steps: list[dict[str, Any]] = []
    for c in cohorts:
        venue_name = None
        city_name = None
        if c.location_id and c.location_id in loc_map:
            venue_name, city_name = loc_map[c.location_id]
        elif c.location:
            venue_name = c.location

        enrolled = reg_counts.get(c.id, 0)
        seats_left = max(0, c.capacity - enrolled) if c.capacity is not None else None
        steps.append(
            {
                "cohort_id": str(c.id),
                "name": c.name,
                "starts_on": c.starts_on.isoformat() if c.starts_on else None,
                "ends_on": c.ends_on.isoformat() if c.ends_on else None,
                "date_label": _format_date_span(c.starts_on, c.ends_on),
                "city": city_name,
                "venue": venue_name,
                "status": c.status,
                "capacity": c.capacity,
                "enrolled_count": enrolled,
                "seats_left": seats_left,
                "sessions_count": sess_counts.get(c.id, 0),
            }
        )

    all_starts = [c.starts_on for c in cohorts if c.starts_on]
    all_ends = [c.ends_on or c.starts_on for c in cohorts if (c.ends_on or c.starts_on)]
    date_label = _format_date_span(min(all_starts) if all_starts else None, max(all_ends) if all_ends else None)

    first_city = next((s["city"] for s in steps if s.get("city")), None)
    first_venue = next((s["venue"] for s in steps if s.get("venue")), None)

    curriculum = await _fetch_lms_curriculum(db, program.id)

    live_data = {
        "title": program.name,
        "about_text": program.description,
        "event_type": PROGRAM_TO_EVENT_TYPE.get((program.program_type or "").lower(), "workshop"),
        "host_org_name": host_org_name,
        "partners": partners,
        "date_label": date_label,
        "city": first_city,
        "location": first_venue,
        "curriculum_chapters": curriculum,
        "steps": steps,
    }

    if use_cache:
        _event_live_cache[cache_key] = (time.monotonic(), live_data)
    return live_data


def apply_event_live_merge(
    event_dict: dict[str, Any],
    *,
    live: dict[str, Any] | None,
    live_linked: bool,
    overrides: dict[str, Any] | None,
    hidden_cohort_ids: list[str] | None,
    hidden_sections: list[str] | None,
    include_admin_meta: bool = False,
) -> dict[str, Any]:
    """Merge live program data + overrides into a serialized WebsiteEvent dict."""
    ov = overrides or {}
    hidden_cohorts = {str(x) for x in (hidden_cohort_ids or [])}
    hidden_secs = set(hidden_sections or [])

    out = dict(event_dict)
    field_states: dict[str, dict[str, Any]] = {}

    if live_linked and live is not None:
        step_descs = ov.get("step_descriptions") if isinstance(ov.get("step_descriptions"), dict) else {}
        raw_steps = []
        for s in (live.get("steps") or []):
            cid = str(s.get("cohort_id"))
            desc = step_descs.get(cid)
            raw_steps.append({
                **s,
                "is_custom": False,
                "description": desc if isinstance(desc, str) and desc.strip() else s.get("description"),
            })
        custom_steps = ov.get("custom_steps") if isinstance(ov.get("custom_steps"), list) else []
        for cs in custom_steps:
            if not isinstance(cs, dict) or not cs.get("id"):
                continue
            raw_steps.append({
                "cohort_id": str(cs["id"]),
                "is_custom": True,
                "name": str(cs.get("name") or "").strip(),
                "description": str(cs.get("description") or "").strip() or None,
                "date_label": str(cs.get("date_label") or "").strip() or None,
                "venue": str(cs.get("venue") or "").strip() or None,
                "city": str(cs.get("city") or "").strip() or None,
                "status": str(cs.get("status") or "").strip() or None,
                "sessions_count": 0,
                "seats_left": None,
            })
        saved_order = ov.get("step_order")
        if isinstance(saved_order, list) and saved_order:
            rank = {str(cid): idx for idx, cid in enumerate(saved_order)}
            raw_steps.sort(key=lambda s: rank.get(str(s.get("cohort_id")), 9999))
        visible_steps = [
            s for s in raw_steps
            if str(s.get("cohort_id")) not in hidden_cohorts
            and (not s.get("is_custom") or s.get("name"))
        ]
        admin_steps = [{**s, "hidden": str(s.get("cohort_id")) in hidden_cohorts} for s in raw_steps]

        list_fields = {"partners", "curriculum_chapters", "steps"}
        for field in EVENT_LIVE_FIELDS:
            live_val = visible_steps if field == "steps" else live.get(field)
            stored_val = out.get(field)
            if field in ov:
                eff_val = ov[field]
                source = "override"
            elif live_val not in (None, "", []):
                eff_val = live_val
                source = "live"
            else:
                eff_val = stored_val if stored_val is not None else ([] if field in list_fields else None)
                source = "manual" if stored_val not in (None, "", []) else "live"

            if field in list_fields and eff_val is None:
                eff_val = []
            out[field] = eff_val
            if include_admin_meta:
                field_states[field] = {
                    "live": live_val,
                    "override": ov.get(field),
                    "effective": eff_val,
                    "source": source,
                }

        if include_admin_meta:
            out["live_steps"] = admin_steps
            out["field_states"] = field_states
        else:
            # Public response omits hidden sections cleanly
            if "steps" in hidden_secs:
                out["steps"] = []
            if "curriculum" in hidden_secs:
                out["curriculum_chapters"] = []
            if "partners" in hidden_secs:
                out["partners"] = []
            if "about" in hidden_secs:
                out["about_text"] = None
            if "faqs" in hidden_secs:
                out["faqs"] = []
            if "registration" in hidden_secs:
                out["registration_url"] = None
                out["registration_text"] = None
    else:
        out.setdefault("steps", [])
        out.setdefault("curriculum_chapters", [])
        if include_admin_meta:
            out["live_steps"] = []
            out["field_states"] = {}

    return out


async def resolve_case_study_live(
    db: AsyncSession,
    *,
    source_type: str,
    program_id: UUID | None,
    cohort_id: UUID | None,
    cohort_ids: list[str] | list[UUID] | None,
    use_cache: bool = False,
    cache_id: str | None = None,
) -> dict[str, Any]:
    """Compute live Case Study metrics, curriculum, partners, and ordered stages
    from a Program and/or ordered list of Cohort IDs."""
    if use_cache and cache_id:
        hit = _cs_live_cache.get(cache_id)
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_SECONDS:
            return hit[1]

    ordered_ids: list[UUID] = []
    program: Program | None = None

    if source_type == "cohort" and cohort_id:
        ordered_ids = [UUID(str(cohort_id))]
    elif cohort_ids:
        for cid in cohort_ids:
            try:
                u = UUID(str(cid))
                if u not in ordered_ids:
                    ordered_ids.append(u)
            except Exception:
                continue
    elif source_type == "program" and program_id:
        c_rows = (
            await db.execute(
                select(Cohort.id)
                .where(
                    Cohort.program_id == program_id,
                    Cohort.status.notin_(["draft", "cancelled"]),
                    ~Cohort.name.ilike("[Template]%"),
                    func.lower(func.trim(Cohort.name)) != "template",
                )
                .order_by(Cohort.starts_on.asc().nullslast(), Cohort.created_at.asc())
            )
        ).scalars().all()
        ordered_ids = list(c_rows)

    cohorts_by_id: dict[UUID, Cohort] = {}
    if ordered_ids:
        for c in (await db.execute(select(Cohort).where(Cohort.id.in_(ordered_ids)))).scalars().all():
            cohorts_by_id[c.id] = c

    ordered_cohorts = [cohorts_by_id[cid] for cid in ordered_ids if cid in cohorts_by_id]
    ordered_ids = [c.id for c in ordered_cohorts]

    if program_id:
        program = await db.get(Program, program_id)
    elif ordered_cohorts:
        program = await db.get(Program, ordered_cohorts[0].program_id)

    sample_cohort = ordered_cohorts[0] if ordered_cohorts else None
    title = program.name if program else (sample_cohort.name if sample_cohort else "Case Study")
    subtitle = (
        f"{len(ordered_cohorts)}-Stage Program"
        if len(ordered_cohorts) > 1
        else (sample_cohort.name if (sample_cohort and program and sample_cohort.name != program.name) else None)
    )
    overview_text = program.description if program and program.description else None
    card_summary = overview_text[:160] if overview_text else f"Hands-on mission program: {title}."
    category = PROGRAM_TO_CS_CATEGORY.get((program.program_type or "").lower(), "National Programs") if program else "Other"

    # Partner / Organization
    partner_name = None
    org_id = (
        next((c.organization_id for c in ordered_cohorts if c.organization_id), None)
        or (program.organization_id if program else None)
    )
    if org_id:
        org = await db.get(Organization, org_id)
        if org:
            partner_name = org.name_latin or org.name_arabic

    partners: list[dict[str, Any]] = []
    if partner_name:
        partners.append({"name": partner_name, "logo_url": "", "role": "In partnership with"})

    metrics: list[dict[str, Any]] = []
    card_metrics: list[dict[str, Any]] = []
    structure_sections: list[dict[str, Any]] = []

    if ordered_ids:
        student_identity = func.coalesce(
            func.nullif(func.lower(func.trim(Contact.email)), ""),
            func.cast(Registration.contact_id, String),
        )
        team_identity = func.coalesce(
            func.nullif(func.lower(func.trim(Team.roster_team_id)), ""),
            func.nullif(func.lower(func.trim(Team.name)), ""),
            func.cast(Team.id, String),
        )

        total_participants = (
            await db.execute(
                select(func.count(func.distinct(student_identity)))
                .outerjoin(Contact, Registration.contact_id == Contact.id)
                .where(
                    Registration.cohort_id.in_(ordered_ids),
                    Registration.status != "cancelled",
                )
            )
        ).scalar() or 0

        trained_count = (
            await db.execute(
                select(func.count(func.distinct(student_identity)))
                .outerjoin(Contact, Registration.contact_id == Contact.id)
                .where(
                    Registration.cohort_id.in_(ordered_ids),
                    or_(Registration.status == "completed", Registration.status == "attended"),
                )
            )
        ).scalar() or 0

        teams_count = (
            await db.execute(
                select(func.count(func.distinct(team_identity))).where(
                    Team.cohort_id.in_(ordered_ids),
                    Team.is_observer.is_(False),
                )
            )
        ).scalar() or 0

        prototypes_count = (
            await db.execute(
                select(func.count(func.distinct(team_identity))).where(
                    Team.cohort_id.in_(ordered_ids),
                    Team.is_observer.is_(False),
                    Team.final_locked_at.is_not(None),
                )
            )
        ).scalar() or 0

        schools_count = (
            await db.execute(
                select(func.count(func.distinct(Contact.organization_id)))
                .join(Registration, Registration.contact_id == Contact.id)
                .where(
                    Registration.cohort_id.in_(ordered_ids),
                    Registration.status != "cancelled",
                    Contact.organization_id.is_not(None),
                )
            )
        ).scalar() or 0

        sessions_count = (
            await db.execute(select(func.count(Session.id)).where(Session.cohort_id.in_(ordered_ids)))
        ).scalar() or 0

        cities_rows = (
            await db.execute(
                select(City.name)
                .join(Location, Location.city_id == City.id)
                .join(Cohort, Cohort.location_id == Location.id)
                .where(Cohort.id.in_(ordered_ids))
                .distinct()
            )
        ).scalars().all()
        cities_list = [c for c in cities_rows if c]

        if trained_count > 0:
            val = (
                f"{trained_count:,}"
                if trained_count == total_participants or total_participants == 0
                else f"{trained_count:,} / {total_participants:,}"
            )
            metrics.append({"value": val, "label": "Students Trained", "is_hero": False})
            card_metrics.append({"value": val, "label": "Students Trained", "is_hero": False})
        elif total_participants > 0:
            metrics.append({"value": f"{total_participants:,}", "label": "Participants", "is_hero": False})
            card_metrics.append({"value": f"{total_participants:,}", "label": "Participants", "is_hero": False})

        if teams_count > 0:
            metrics.append({"value": f"{teams_count}", "label": "Teams", "is_hero": False})
            if len(card_metrics) < 2:
                card_metrics.append({"value": f"{teams_count}", "label": "Teams", "is_hero": False})

        if prototypes_count > 0:
            metrics.append({"value": f"{prototypes_count}", "label": "Prototypes Built", "is_hero": False})

        if schools_count > 0:
            metrics.append({"value": f"{schools_count}", "label": "Schools / Universities", "is_hero": False})
            if len(card_metrics) < 2:
                card_metrics.append({"value": f"{schools_count}", "label": "Schools", "is_hero": False})

        if sessions_count > 0:
            metrics.append({"value": f"{sessions_count}", "label": "Sessions Delivered", "is_hero": False})

        if cities_list:
            metrics.append({"value": f"{len(cities_list)} Cities", "label": " • ".join(cities_list[:3]), "is_hero": False})

        # Per-stage breakdown (ordered by ordered_cohorts)
        sessions_by_cohort: dict[UUID, list[Session]] = {}
        c_sessions = (
            await db.execute(
                select(Session)
                .where(Session.cohort_id.in_(ordered_ids))
                .order_by(Session.meeting_date.asc(), Session.starts_at.asc())
            )
        ).scalars().all()
        for sess in c_sessions:
            sessions_by_cohort.setdefault(sess.cohort_id, []).append(sess)

        loc_ids = [c.location_id for c in ordered_cohorts if c.location_id]
        loc_map: dict[UUID, tuple[str, str | None]] = {}
        if loc_ids:
            for lid, lname, cname in (
                await db.execute(
                    select(Location.id, Location.name, City.name)
                    .outerjoin(City, Location.city_id == City.id)
                    .where(Location.id.in_(loc_ids))
                )
            ).all():
                loc_map[lid] = (lname, cname)

        for idx, c in enumerate(ordered_cohorts):
            sess_list = sessions_by_cohort.get(c.id, [])
            venue, city = loc_map.get(c.location_id, (c.location, None)) if c.location_id else (c.location, None)
            span = _format_date_span(c.starts_on, c.ends_on)
            subtitle_parts = [p for p in [span, city or venue] if p]
            day_rows = []
            for d_idx, s in enumerate(sess_list):
                day_title = f"Day {d_idx + 1} - {s.title}" if s.title else f"Day {d_idx + 1}"
                milestones = [s.meeting_date.strftime("%b %d, %Y")] if s.meeting_date else []
                day_rows.append({"day_title": day_title, "milestones": milestones})
            structure_sections.append(
                {
                    "id": f"stage-{idx + 1}",
                    "badge": f"Stage {idx + 1:02d}",
                    "title": c.name,
                    "subtitle": " · ".join(subtitle_parts) if subtitle_parts else None,
                    "image_url": None,
                    "items": [],
                    "days": day_rows,
                }
            )

    curriculum_chapters = await _fetch_lms_curriculum(db, program.id) if program else []

    live_data = {
        "title": title,
        "subtitle": subtitle,
        "category": category,
        "card_summary": card_summary,
        "overview_text": overview_text,
        "partner_name": partner_name,
        "partners": partners,
        "metrics": metrics,
        "card_metrics": card_metrics,
        "curriculum_chapters": curriculum_chapters,
        "structure_sections": structure_sections,
    }

    if use_cache and cache_id:
        _cs_live_cache[cache_id] = (time.monotonic(), live_data)
    return live_data


def apply_case_study_live_merge(
    cs_dict: dict[str, Any],
    *,
    live: dict[str, Any] | None,
    live_linked: bool,
    overrides: dict[str, Any] | None,
    hidden_sections: list[str] | None,
    include_admin_meta: bool = False,
) -> dict[str, Any]:
    """Merge live Case Study data + overrides into a serialized WebsiteCaseStudy dict."""
    ov = overrides or {}
    hidden_secs = set(hidden_sections or [])
    out = dict(cs_dict)
    field_states: dict[str, dict[str, Any]] = {}

    if live_linked and live is not None:
        for field in CASE_STUDY_LIVE_FIELDS:
            live_val = live.get(field)
            stored_val = out.get(field)
            if field in ov:
                eff_val = ov[field]
                source = "override"
            elif live_val not in (None, "", []):
                eff_val = live_val
                source = "live"
            else:
                eff_val = stored_val
                source = "manual" if stored_val not in (None, "", []) else "live"

            out[field] = eff_val
            if include_admin_meta:
                field_states[field] = {
                    "live": live_val,
                    "override": ov.get(field),
                    "effective": eff_val,
                    "source": source,
                }

        if include_admin_meta:
            out["field_states"] = field_states
        else:
            if "metrics" in hidden_secs:
                out["metrics"] = []
                out["card_metrics"] = []
            if "curriculum" in hidden_secs:
                out["curriculum_chapters"] = []
            if "structure" in hidden_secs:
                out["structure_sections"] = []
            if "partners" in hidden_secs:
                out["partners"] = []
            if "gallery" in hidden_secs:
                out["gallery_images"] = []
            if "testimonials" in hidden_secs:
                out["testimonials"] = []
    elif include_admin_meta:
        out["field_states"] = {}

    return out
