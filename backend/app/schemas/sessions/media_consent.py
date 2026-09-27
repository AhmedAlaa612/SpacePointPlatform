"""Schemas for Cohort Media Consent (2026-09-27)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MediaConsentWebhookRequest(BaseModel):
    """Payload received from Google Form via Google Apps Script or external webhook."""

    student_name: str | None = None
    school_name: str | None = None
    parent_name: str = "Parent / Guardian"
    relationship: str | None = None
    mobile_number: str | None = None
    email_address: str | None = None
    permission_grants: list[str] | str | None = Field(default_factory=list)
    consent_choice: str = "consented"
    declaration_agreed: bool = True
    date_of_signing: date | str | None = None
    raw_payload: dict[str, Any] | None = None


class MediaConsentManualOverrideRequest(BaseModel):
    """Operations staff manual override of student consent state."""

    registration_id: UUID
    consent_choice: Literal["consented", "declined", "pending"]
    parent_name: str | None = None
    relationship: str | None = None
    parent_phone: str | None = None
    parent_email: str | None = None
    notes: str | None = None


class MediaConsentManualMatchRequest(BaseModel):
    """Link an unmatched consent record to a specific registration in the cohort."""

    registration_id: UUID


class CohortMediaConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cohort_id: UUID
    registration_id: UUID | None = None
    matched_contact_id: UUID | None = None
    matched_student_name: str | None = None
    student_name_raw: str | None = None
    school_name_raw: str | None = None
    parent_name: str
    relationship: str | None = None
    parent_phone: str | None = None
    parent_email: str | None = None
    consent_choice: str
    permission_grants: list[str] = Field(default_factory=list)
    declaration_agreed: bool = True
    date_of_signing: date | None = None
    source: str
    match_status: str
    match_method: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class CohortMediaConsentSummaryOut(BaseModel):
    total_submissions: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    consented_count: int = 0
    declined_count: int = 0
    pending_registrations_count: int = 0
    total_registrations_count: int = 0
    items: list[CohortMediaConsentOut] = Field(default_factory=list)
