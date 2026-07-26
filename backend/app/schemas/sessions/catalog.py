"""Public catalog schema (V2 R3-1) — GET /public/catalog. No auth; the
minimum a marketing site needs to list open cohorts and link a registration
form at each one. Never exposes anything beyond what's already public-facing
(program name/description, cohort dates/location, price, capacity headroom)
— no ids into anything private, no registrant data.
"""

from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class CatalogCohortOut(BaseModel):
    cohort_id: UUID
    program_name: str
    program_type: str
    description: Optional[str] = None
    starts_on: Optional[date] = None
    ends_on: Optional[date] = None
    location: Optional[str] = None
    # "Free" or "AED 250" — pre-formatted so the website doesn't need its own
    # pricing_model/price branching logic duplicated from Programs.tsx.
    price_display: str
    # None = uncapped cohort, no spots-left concept. Never negative — clamped
    # at 0 if active registrations have (somehow) reached/exceeded capacity.
    spots_left: Optional[int] = None
    # True once spots_left/capacity drops under 10% — a "filling up" signal.
    is_limited: bool = False
    # Where the website's own registration form should POST to (V2 R1-5).
    registration_endpoint: str
