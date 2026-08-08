"""Public catalog schema (V2 R3-1) — GET /public/catalog. No auth; the
minimum a marketing site needs to list open cohorts and link a registration
form at each one. Never exposes anything beyond what's already public-facing
(program name/description, cohort dates/location, price, capacity headroom)
— no ids into anything private, no registrant data.
"""

from __future__ import annotations

from datetime import date, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CatalogSessionOut(BaseModel):
    meeting_date: date
    starts_at: Optional[time] = None
    title: Optional[str] = None


class CatalogCohortOut(BaseModel):
    cohort_id: UUID
    program_name: str
    program_type: str
    description: Optional[str] = None
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    location: Optional[str] = None
    # ── rich location (2026-08-08), resolved from Cohort.location_id -> the
    # `locations` table when set, else the legacy Cohort.location/
    # location_map_url text fields — see public_catalog() for the fallback.
    location_name: Optional[str] = None
    location_address: Optional[str] = None
    location_maps_url: Optional[str] = None
    # "Free" or "AED 250" — pre-formatted so the website doesn't need its own
    # pricing_model/price branching logic duplicated from Programs.tsx.
    price_display: str
    capacity: Optional[int] = None
    # None = uncapped cohort, no spots-left concept. Never negative — clamped
    # at 0 if active registrations have (somehow) reached/exceeded capacity.
    spots_left: Optional[int] = None
    # True once spots_left/capacity drops under 10% — a "filling up" signal.
    is_limited: bool = False
    # Where the website's own registration form should POST to (V2 R1-5).
    registration_endpoint: str

    # ── 2026-08-07: planned vs registration_open dual CTA + rich cards ──────
    # planned|registration_open — drives which CTA the card shows.
    status: str
    # POST target for "Notify me" (status == planned only).
    interest_endpoint: str
    sessions: list[CatalogSessionOut] = []
    instructors: list[str] = []
    curriculum_titles: list[str] = []


class PublicTicketOut(BaseModel):
    """What the public ticket page (/t/{token}) shows. Deliberately narrow —
    this endpoint needs no auth (the token in the URL is the credential), so
    it exposes only what's already printed on the ticket the student was
    emailed: no contact id, no phone, no email, no payment detail."""

    student_name: str
    program_name: str
    cohort_name: str
    dates: str
    location: str | None = None
    # Full resolved location (2026-08-08) — the ticket page shows the
    # address and a maps link under the name, same as the emailed ticket.
    location_address: str | None = None
    location_maps_url: str | None = None
    ticket_token: str
    status: str
    checked_in: bool
