"""The SP-####-UAE / SP-ST-####-UAE card-id text format.

Split out of id_card.py (which also does the actual PNG/QR-code
rendering, pulling in cairosvg/PIL/qrcode at module import time) so
importing this one pure formatter doesn't drag those in too — the hot
auth path (core/dependencies.py, for the structured-logging user_label
on every authenticated request) only ever needs this text, never a
rendered card image.
"""


def format_card_id(card_number: int, roles: list[str]) -> str:
    """The one place `SP-####-UAE` (staff) vs `SP-ST-####-UAE` (student) vs
    `SP-ORG-####-UAE` (organization) vs `SP-OB-####-UAE` (observer) gets
    formatted — used at read time (routers/auth.py, routers/admin/users.py),
    at physical-card generation time (id_card.py::ensure_card_id), and for
    the structured-logging user_label (core/dependencies.py), so the prefix
    logic can't drift between them. `roles` decides the prefix, never the
    number itself — student, staff and organization numbers are drawn from
    separate sequences (2026-08-22 students, 2026-10 organizations; operator:
    students, staff and orgs must not look like they share a numbering pool)
    but a bare integer can't carry that distinction on its own once printed.

    A pure organization account (holds ONLY `organization`) gets
    `SP-ORG-####-UAE`. Multi-role accounts carrying `organization` plus a
    staff/student role keep the staff/student prefix — same "pure label,
    mixed falls back" posture as observer mode below.

    Observer mode (2026-10): a pure observer (holds `observer` and none of
    the staff/student roles) gets `SP-OB-####-UAE`. Multi-role staff
    testing as observers keep their existing staff card `SP-####-UAE`."""
    role_set = set(roles or [])
    staff_roles = {"operations", "admin", "facilitator", "instructor", "student"}
    if role_set == {"organization"}:
        prefix = "SP-ORG-"
    elif "observer" in role_set and not (staff_roles & role_set):
        prefix = "SP-OB-"
    elif "student" in role_set:
        prefix = "SP-ST-"
    else:
        prefix = "SP-"
    return f"{prefix}{card_number:04d}-UAE"
