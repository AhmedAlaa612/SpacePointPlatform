"""The SP-####-UAE / SP-ST-####-UAE card-id text format.

Split out of id_card.py (which also does the actual PNG/QR-code
rendering, pulling in cairosvg/PIL/qrcode at module import time) so
importing this one pure formatter doesn't drag those in too — the hot
auth path (core/dependencies.py, for the structured-logging user_label
on every authenticated request) only ever needs this text, never a
rendered card image.
"""


def format_card_id(card_number: int, roles: list[str]) -> str:
    """The one place `SP-####-UAE` (staff) vs `SP-ST-####-UAE` (student) gets
    formatted — used at read time (routers/auth.py, routers/admin/users.py),
    at physical-card generation time (id_card.py::ensure_card_id), and for
    the structured-logging user_label (core/dependencies.py), so the prefix
    logic can't drift between them. `roles` decides the prefix, never the
    number itself — student and staff numbers are drawn from separate
    sequences (2026-08-22, operator: students and staff must not look like
    they share a numbering pool) but a bare integer can't carry that
    distinction on its own once printed."""
    prefix = "SP-ST-" if "student" in roles else "SP-"
    return f"{prefix}{card_number:04d}-UAE"
