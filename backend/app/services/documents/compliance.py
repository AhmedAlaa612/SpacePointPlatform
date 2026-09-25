"""Instructor document compliance service.

Evaluates whether an instructor has uploaded all required compliance documents:
1. Passport (Mandatory for all)
2. Emirates ID / National ID (Mandatory for all: Emirates ID for UAE residents, National ID for international)
3. Personal Picture (Passport-style photo — mandatory for all)
4. Clearance Document (Police Clearance / Good Conduct Certificate — mandatory for all)
5. Residence Visa (Mandatory for UAE residents; exempt/optional for international instructors)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Sequence

from app.models.instructors.instructor_document import InstructorDocument
from app.models.user import User

DOC_TYPE_ALIASES: dict[str, list[str]] = {
    "passport": ["passport"],
    "emirates_id": ["emirates id / national id", "emirates id", "national id", "id card"],
    "photo": ["personal picture", "photo", "passport photo", "personal photo", "passport style photo"],
    "clearance_1": [
        "clearance document 1", "clearance document 1 (form 1)", "clearance form 1", "clearance 1",
        "form 1", "security clearance 1", "clerance 1", "clearance_1", "security clearance form 1",
    ],
    "clearance_2": [
        "clearance document 2", "clearance document 2 (form 2)", "clearance form 2", "clearance 2",
        "form 2", "security clearance 2", "clerance 2", "clearance_2", "security clearance form 2",
    ],
    "clearance": ["clearance document", "clearance", "police clearance", "good conduct certificate", "certificate of good conduct"],
    "visa": ["residence visa", "visa", "uae residence visa", "residency visa"],
}

CHECKLIST_SPECS = [
    {
        "key": "passport",
        "label": "Passport",
        "desc": "High-quality copy of your passport information page.",
        "always_mandatory": True,
    },
    {
        "key": "emirates_id",
        "label": "Emirates ID / National ID",
        "desc": "UAE Emirates ID (front & back) if residing in the UAE, or local National ID if international.",
        "always_mandatory": True,
    },
    {
        "key": "photo",
        "label": "Personal Picture (Passport style)",
        "desc": "Professional high-resolution headshot for portal ID card and verification.",
        "always_mandatory": True,
    },
    {
        "key": "clearance_1",
        "label": "Clearance Document 1",
        "desc": "Security clearance form 1 (PDF) — download template, fill, and upload.",
        "always_mandatory": True,
    },
    {
        "key": "clearance_2",
        "label": "Clearance Document 2",
        "desc": "Security clearance form 2 (Word) — download template, fill, and upload.",
        "always_mandatory": True,
    },
    {
        "key": "visa",
        "label": "Residence Visa",
        "desc": "UAE Residency Visa copy (mandatory for UAE expats; exempt for international instructors and citizens).",
        "always_mandatory": False,  # Country-dependent
    },
]


def _extract_display_filename(file_path: str | None, file_url: str | None, fallback: str) -> str:
    candidate = file_path or (file_url.split("?")[0] if file_url else None)
    if candidate:
        name = candidate.split("/")[-1]
        # Remove leading UUID or numeric prefixes
        name = re.sub(r"^[0-9a-fA-F\-]{36}_?", "", name)
        name = re.sub(r"^\d+_", "", name)
        name = name.replace("_", " ").strip()
        if name:
            return name
    return fallback


def _match_key(doc_type: str, file_path: str | None = None, file_url: str | None = None) -> str | None:
    norm = doc_type.strip().lower()
    for key in ("clearance_1", "clearance_2"):
        if norm in DOC_TYPE_ALIASES[key] or any(norm.startswith(a) for a in DOC_TYPE_ALIASES[key]):
            return key
    for key, aliases in DOC_TYPE_ALIASES.items():
        if norm in aliases or any(norm.startswith(a) for a in aliases):
            return key
    # Also check if filename strongly hints at the document type
    candidate = file_path or (file_url.split("?")[0] if file_url else "")
    fname = candidate.split("/")[-1].lower()
    if fname:
        if "clearance_1" in fname or "form_1" in fname or "form 1" in fname or "clerance.pdf" in fname or "clerance_1" in fname:
            return "clearance_1"
        if "clearance_2" in fname or "form_2" in fname or "form 2" in fname or "clerance_2" in fname:
            return "clearance_2"
        for key in ["passport", "visa", "clearance", "photo"]:
            for alias in DOC_TYPE_ALIASES.get(key, []):
                if alias in fname:
                    return key
    return None


def is_user_uae_resident(user: User, city_country: str | None = None) -> bool:
    """Determine if user resides in the UAE based on country/city fields."""
    country = (user.country or "").strip().upper()
    if country in ("AE", "ARE", "UNITED ARAB EMIRATES", "UAE"):
        return True
    if city_country and city_country.strip().upper() == "AE":
        return True
    return False


@dataclass
class ChecklistItem:
    key: str
    label: str
    desc: str
    mandatory: bool
    uploaded: bool
    exempt: bool = False
    exemption_reason: str | None = None
    document_id: str | None = None
    document_type: str | None = None
    file_url: str | None = None
    uploaded_at: str | None = None


def evaluate_instructor_compliance(
    user: User,
    documents: Sequence[InstructorDocument],
    city_country: str | None = None,
) -> dict[str, Any]:
    """Calculate compliance metrics and structured checklist for an instructor."""
    uae_resident = is_user_uae_resident(user, city_country)

    matched_by_key: dict[str, InstructorDocument] = {}
    other_docs: list[dict[str, Any]] = []

    # Sort documents latest-first so newest matching document takes precedence
    sorted_docs = sorted(documents, key=lambda d: d.uploaded_at or datetime.min, reverse=True)

    for doc in sorted_docs:
        key = _match_key(doc.document_type, doc.file_path, doc.file_url)
        if key == "clearance":
            if "clearance_1" not in matched_by_key:
                key = "clearance_1"
            elif "clearance_2" not in matched_by_key:
                key = "clearance_2"
        if key and key not in matched_by_key:
            matched_by_key[key] = doc
        else:
            display_name = _extract_display_filename(doc.file_path, doc.file_url, doc.document_type)
            other_docs.append({
                "id": str(doc.id),
                "document_type": doc.document_type,
                "file_name": display_name,
                "file_url": doc.file_url,
                "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            })

    checklist: list[dict[str, Any]] = []
    missing_docs: list[str] = []
    total_required = 0
    uploaded_count = 0

    for spec in CHECKLIST_SPECS:
        key = spec["key"]
        is_mandatory = spec["always_mandatory"]

        exempt = False
        exemption_reason = None
        if key == "visa":
            if not uae_resident:
                is_mandatory = False
                exempt = True
                exemption_reason = "Exempt — instructor is not residing in the UAE."
            else:
                is_mandatory = True

        doc = matched_by_key.get(key)
        uploaded = doc is not None

        if is_mandatory:
            total_required += 1
            if uploaded:
                uploaded_count += 1
            else:
                missing_docs.append(spec["label"])

        item = ChecklistItem(
            key=key,
            label=spec["label"],
            desc=spec["desc"],
            mandatory=is_mandatory,
            uploaded=uploaded,
            exempt=exempt,
            exemption_reason=exemption_reason,
            document_id=str(doc.id) if doc else None,
            document_type=doc.document_type if doc else None,
            file_url=doc.file_url if doc else None,
            uploaded_at=doc.uploaded_at.isoformat() if doc and doc.uploaded_at else None,
        )
        checklist.append(asdict(item))

    is_complete = len(missing_docs) == 0

    return {
        "is_complete": is_complete,
        "is_uae_resident": uae_resident,
        "total_required": total_required,
        "uploaded_count": uploaded_count,
        "missing_docs": missing_docs,
        "checklist": checklist,
        "other_documents": other_docs,
    }
