"""Verifier registry (P5-2) — one entry per `missions.kind`, mirroring the
`_CONTENT_MODEL` dict `routers/lms/admin.py` already uses for module-item
kinds. Each verifier module owns its own submit/decide functions; nothing
here enforces a shared base class since `submission` (human-reviewed) and
`quiz` (auto-graded) genuinely take different inputs — the registry is only
"kind string -> the module that knows how to run it", for router dispatch.
"""

from app.services.missions.verifiers import design, quiz, submission

VERIFIER_KINDS = {"submission", "quiz", "checklist", "design", "external"}

__all__ = ["VERIFIER_KINDS", "design", "quiz", "submission"]
