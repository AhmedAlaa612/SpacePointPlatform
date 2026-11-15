"""ARQ background task for rendering and emailing competition certificates.

Handles cohort certificate dispatch off the HTTP request path so long ReportLab PDF
renderings and SMTP dispatches execute reliably in the background without HTTP timeouts.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.db.session import AsyncSessionLocal
from app.services.competitions.certificates import send_cohort_certificates

logger = logging.getLogger("workers.certificates")


async def send_cohort_certificates_job(
    ctx: dict[str, Any] | None,
    cohort_id: str,
    actor_user_id: str,
    filter_type: str = "at_least_one",
    registration_ids: list[str] | None = None,
    team_ids: list[str] | None = None,
    theme: str = "dark",
    template_id: str | None = None,
    primary_kind: str = "individual",
    primary_template_id: str | None = None,
    primary_email_template_id: str | None = None,
    also_send_other: bool = False,
    secondary_template_id: str | None = None,
    secondary_email_template_id: str | None = None,
    delivery_mode: str = "email",
    notify_by_email: bool = True,
    skip_already_issued: bool = True,
    custom_email_subject: str | None = None,
    custom_email_body: str | None = None,
    save_email_to_template: bool = False,
    force_certificate_type: str | None = None,
) -> dict[str, Any]:
    """ARQ background job to issue and send certificates for a cohort."""
    logger.info(
        "Starting background certificate dispatch for cohort %s (filter=%s, targets=%s)",
        cohort_id,
        filter_type,
        len(registration_ids) if registration_ids else "all_matching",
    )

    def _parse_uuids(items: list[str] | None) -> list[uuid.UUID] | None:
        if not items:
            return None
        out = []
        for r in items:
            try:
                out.append(uuid.UUID(str(r)))
            except (ValueError, TypeError):
                pass
        return out

    def _parse_uuid(val: str | None) -> uuid.UUID | None:
        if not val:
            return None
        try:
            return uuid.UUID(str(val))
        except (ValueError, TypeError):
            return None

    reg_uuids = _parse_uuids(registration_ids)
    team_uuids = _parse_uuids(team_ids)

    try:
        async with AsyncSessionLocal() as db:
            result = await send_cohort_certificates(
                db,
                cohort_id=uuid.UUID(cohort_id),
                actor_user_id=uuid.UUID(actor_user_id),
                filter_type=filter_type,
                registration_ids=reg_uuids,
                team_ids=team_uuids,
                theme=theme,
                template_id=template_id,
                primary_kind=primary_kind,
                primary_template_id=primary_template_id,
                primary_email_template_id=_parse_uuid(primary_email_template_id),
                also_send_other=also_send_other,
                secondary_template_id=secondary_template_id,
                secondary_email_template_id=_parse_uuid(secondary_email_template_id),
                delivery_mode=delivery_mode,
                notify_by_email=notify_by_email,
                skip_already_issued=skip_already_issued,
                custom_email_subject=custom_email_subject,
                custom_email_body=custom_email_body,
                save_email_to_template=save_email_to_template,
                force_certificate_type=force_certificate_type,
            )
            logger.info(
                "Completed certificate dispatch for cohort %s: %d sent, %d skipped, %d errors",
                cohort_id,
                result.get("sent_count", 0),
                result.get("skipped_count", 0),
                len(result.get("errors", [])),
            )
            return result
    except Exception as exc:
        logger.exception("Failed during background certificate dispatch for cohort %s: %s", cohort_id, exc)
        return {
            "sent_count": 0,
            "skipped_count": 0,
            "total_targeted": len(reg_uuids) if reg_uuids else 0,
            "recipient_names": [],
            "errors": [str(exc)],
        }
