"""The fixed set of 25 system email templates (PLAN: Email Templates System).

Single source of truth for three consumers:
  1. The migration that creates `email_templates` seeds these rows directly
     (same pattern as `d8a2c94e0035`/`d2e6f81a0029` — production runs
     `alembic upgrade head` on every deploy, so the table must never be
     empty on a fresh environment).
  2. `db/seed_email_templates.py` — a manual re-seed/backfill convenience,
     mirroring `seed_templates.py`.
  3. `services/email_templates.py::render_and_send` — the fallback used if a
     `key` has no DB row yet (an environment whose migration hasn't run),
     so a missing row degrades to "send the default copy", never "send
     nothing and don't say why".

Every `key` here is referenced by exactly one call site in the code (see
`services/email.py` and the handful of other modules that send email
directly). This table is edit + pause only — never create/delete — so
nothing here is meant to grow without a matching code change.

`placeholders` and `attachment_labels` are informational only: they tell
the admin UI what a template's own call site actually substitutes / attaches,
not a promise the admin's edited body will use every one of them.
"""

EMAIL_TEMPLATE_DEFAULTS: list[dict] = [
    # ── Applications & Instructors ──────────────────────────────────────
    {
        "key": "phase1_approval",
        "name": "Phase 1 Approved",
        "category": "Instructors",
        "description": "Sent when admin approves an instructor applicant's Phase 1 review — asks for the presentation submission next.",
        "subject": "SpacePoint Instructor Application - Phase 1 Approved",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Congratulations — your Phase 1 application has been approved!</p>"
            "<p>Next step: record and submit a 10-15 minute presentation (max 10 slides) "
            "covering CubeSat fundamentals, subsystems, onboard memory, and communications.</p>"
            "<p>Submit it here: <a href=\"{status_link}\">{status_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "status_link"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "moved_to_onboarding",
        "name": "Moved to Onboarding",
        "category": "Applications",
        "description": "Sent when an ambassador/intern/teacher/facilitator applicant clears initial screening and moves to onboarding.",
        "subject": "SpacePoint Internship Application - Onboarding",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Thanks for applying for the SpacePoint internship program.</p>"
            "<p>Your application passed the initial screening and has been moved to the onboarding phase.</p>"
            "<p>Log in to your account and complete it within 10 days: <a href=\"{login_link}\">{login_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "login_link"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "application_approved",
        "name": "Application Approved",
        "category": "Applications",
        "description": "Sent when admin approves an ambassador/intern/teacher/facilitator application outright.",
        "subject": "SpacePoint {role} Application Approved",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Congratulations — your {role} application has been approved! Welcome to SpacePoint.</p>"
            "<p>Log in with the email and password you used to apply: <a href=\"{login_link}\">{login_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "role", "login_link"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "approval_credentials",
        "name": "Instructor Approved — Credentials",
        "category": "Instructors",
        "description": "Sent when an instructor application is approved — includes login info (a temporary password, or a note to use the existing one) and the signed agreement if one was generated at approval time.",
        "subject": "SpacePoint Instructor Application Approved",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Congratulations — your instructor application has been approved!</p>"
            "<p>{login_info}</p>"
            "<p>Log in to the instructor portal: <a href=\"{login_link}\">{login_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "login_info", "login_link"],
        "attachment_labels": ["Signed Instructor Agreement (PDF) — when generated at approval time"],
        "is_internal": False,
    },
    {
        "key": "instructor_welcome",
        "name": "Instructor Welcome (Bulk Import)",
        "category": "Instructors",
        "description": "Sent from a bulk instructor import — the account was created directly by an admin, so there's no existing password to point at.",
        "subject": "Welcome to SpacePoint — set your password",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>An instructor account has been created for you on the SpacePoint portal.</p>"
            "<p>Set your password here: <a href=\"{set_password_link}\">{set_password_link}</a><br>"
            "(This link is valid for 24 hours.)</p>"
            "<p>Once you're in, please go to your Profile and fill in your city and the cities you're able to deliver workshops in.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "set_password_link"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "intern_welcome",
        "name": "Intern Welcome (Bulk Import)",
        "category": "Interns",
        "description": "Sent from a bulk intern import — the account was created directly by an admin, so there's no existing password to point at.",
        "subject": "Welcome to SpacePoint — set your password",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>An intern account has been created for you on the SpacePoint portal.</p>"
            "<p>Set your password here: <a href=\"{set_password_link}\">{set_password_link}</a><br>"
            "(This link is valid for 3 days.)</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "set_password_link"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "contract_signed",
        "name": "Instructor Contract Signed",
        "category": "Instructors",
        "description": "Sent to the instructor once they sign their contract in-app.",
        "subject": "Your Signed SpacePoint Instructor Agreement",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Attached is your fully signed SpacePoint Instructor Agreement.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name"],
        "attachment_labels": ["Signed Instructor Agreement (PDF)"],
        "is_internal": False,
    },
    {
        "key": "contract_signed_notify_admin",
        "name": "Instructor Contract Signed — Admin Notice",
        "category": "Instructors",
        "description": "Internal ping: notifies admin when an instructor signs their contract, so it can be reviewed in the Instructors directory.",
        "subject": "Instructor Contract Signed",
        "body_html": (
            "<p>{instructor_name} has signed their instructor contract. Review it in the admin Instructors directory.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["instructor_name"],
        "attachment_labels": [],
        "is_internal": True,
    },
    {
        "key": "certificates_ready",
        "name": "Delivery Certificates Ready",
        "category": "Instructors",
        "description": "Sent when an instructor requests/downloads their workshop delivery certificate(s).",
        "subject": "Your SpacePoint Certificate(s)",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Attached are your certificate(s) for the workshop(s) you delivered.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name"],
        "attachment_labels": ["Certificate PDF(s) — one per workshop, count varies"],
        "is_internal": False,
    },
    {
        "key": "workshop_certificate_ready",
        "name": "Workshop Certificate Ready",
        "category": "Instructors",
        "description": "Sent when a single workshop-delivery certificate is generated for an instructor.",
        "subject": "Your SpacePoint Certificate of Achievement",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Your certificate of achievement for “{workshop_name}” is ready — see the attached PDF.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "workshop_name"],
        "attachment_labels": ["Certificate PDF"],
        "is_internal": False,
    },

    # ── Internship ───────────────────────────────────────────────────────
    {
        "key": "internship_letter_ready",
        "name": "Internship Letter Ready",
        "category": "Internship",
        "description": "Sent when admin approves an internship role request — the letter is ready for the intern's signature.",
        "subject": "SpacePoint Internship Letter Ready for Signature",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Your internship request has been approved! Your internship letter is ready for your signature.</p>"
            "<p>View and sign it here: <a href=\"{documents_link}\">{documents_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "documents_link"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "internship_letter_signed",
        "name": "Internship Letter Signed",
        "category": "Internship",
        "description": "Sent to the intern once they sign their internship letter in-app.",
        "subject": "Welcome to SpacePoint — Signed Internship Letter",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Welcome aboard! Your internship letter has been signed by both parties — the signed copy is attached for your records.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name"],
        "attachment_labels": ["Signed Internship Letter (PDF)"],
        "is_internal": False,
    },
    {
        "key": "internship_signed_notify_admin",
        "name": "Internship Letter Signed — Admin Notice",
        "category": "Internship",
        "description": "Internal ping: notifies admin when an intern signs their internship letter.",
        "subject": "Internship Letter Signed",
        "body_html": (
            "<p>{intern_name} has signed their internship letter. Review it in the admin panel.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["intern_name"],
        "attachment_labels": [],
        "is_internal": True,
    },

    # ── Payments ─────────────────────────────────────────────────────────
    {
        "key": "payment_letter_ready",
        "name": "Payment Letter Ready",
        "category": "Payments",
        "description": "Sent when admin generates an instructor's payment letter — ready for signature.",
        "subject": "SpacePoint Payment Letter Ready for Signature",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>A new payment letter is ready for your signature.</p>"
            "<p>View and sign it here: <a href=\"{payments_link}\">{payments_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "payments_link"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "payment_signed_notify_admin",
        "name": "Payment Letter Signed — Admin Notice",
        "category": "Payments",
        "description": "Internal ping: notifies admin when an instructor signs their payment letter.",
        "subject": "Payment Letter Signed",
        "body_html": (
            "<p>{instructor_name} has signed their payment letter. Review it in the admin Payments tab.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["instructor_name"],
        "attachment_labels": [],
        "is_internal": True,
    },

    # ── Documents ────────────────────────────────────────────────────────
    {
        "key": "recommendation_letter_ready",
        "name": "Recommendation Letter Ready",
        "category": "Documents",
        "description": "Sent when admin generates a recommendation letter — the letter itself lives on the recipient's My Documents page.",
        "subject": "Your SpacePoint Recommendation Letter",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>A recommendation letter has been generated for you — you can view and download it from your profile.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name"],
        "attachment_labels": [],
        "is_internal": False,
    },

    # ── Sessions, Staffing & Tickets ─────────────────────────────────────
    {
        "key": "session_assignment",
        "name": "Session Assignment",
        "category": "Sessions & Staffing",
        "description": "Sent when ops assigns an instructor to a session, via the marketplace or a direct assign.",
        "subject": "You're assigned: {program_name}",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>You've been assigned to a session of “{program_name}” on {meeting_date}{where}.</p>"
            "<p>See it on your calendar: <a href=\"{my_sessions_link}\">{my_sessions_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "program_name", "meeting_date", "where"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "call_invite",
        "name": "Staffing Call Invite",
        "category": "Sessions & Staffing",
        "description": "Sent when ops opens a staffing call and targets a specific instructor directly.",
        "subject": "You're invited: {program_name}",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>You're invited to take part in “{program_name}” on {meeting_date}{where}.</p>"
            "<p>Visit the portal to register your interest: <a href=\"{available_sessions_link}\">{available_sessions_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "program_name", "meeting_date", "where"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "cohort_interest_open",
        "name": "Cohort Registration Open",
        "category": "Sessions & Staffing",
        "description": "Sent to everyone who registered “notify me” interest in a cohort, the moment ops opens it for registration.",
        "subject": "Registration is open: {program_name}",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Registration is now open for “{program_name}” — you asked to be notified when it did.</p>"
            "<p>Register here: <a href=\"{catalog_link}\">{catalog_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "program_name", "catalog_link"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "ticket_confirmation",
        "name": "Registration Ticket",
        "category": "Sessions & Staffing",
        "description": "Sent when a registration is confirmed — the QR ticket email. Also re-sent in batches from a completed import batch.",
        "subject": "Your SpacePoint ticket — {program_name}",
        "body_html": (
            "<p>Hi {student_name},</p>"
            "<p>You're registered for <strong>{program_name}</strong>.</p>"
            "<p><strong>When:</strong> {dates}<br><strong>Where:</strong> {where}</p>"
            "<p style=\"text-align:center\">{ticket_qr}</p>"
            "<p>Show this ticket at the door. You can also view it online: "
            "<a href=\"{ticket_link}\">{ticket_link}</a></p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["student_name", "program_name", "dates", "where", "ticket_qr", "ticket_link"],
        "attachment_labels": ["QR ticket — inline image, not a file attachment"],
        "is_internal": False,
    },

    # ── Accounts ─────────────────────────────────────────────────────────
    {
        "key": "account_welcome_set_password",
        "name": "Account Created — Set Password",
        "category": "Accounts",
        "description": "Sent when a new portal/student/judge account is created for someone (registration LMS sync, spine contact promotion, judge invite).",
        "subject": "Your SpacePoint learning account",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>An account was created for you on SpacePoint. Set your password here: "
            "<a href=\"{set_password_link}\">{set_password_link}</a></p>"
            "<p>This link is valid for 24 hours.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "set_password_link"],
        "attachment_labels": [],
        "is_internal": False,
    },
    {
        "key": "account_password_reset",
        "name": "Password Reset",
        "category": "Accounts",
        "description": "Sent when someone requests a password reset for an existing account.",
        "subject": "Your SpacePoint learning account",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Here's the link to reset your SpacePoint password: "
            "<a href=\"{set_password_link}\">{set_password_link}</a></p>"
            "<p>This link is valid for 24 hours.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "set_password_link"],
        "attachment_labels": [],
        "is_internal": False,
    },

    # ── Inventory nudges (internal) ──────────────────────────────────────
    {
        "key": "kits_uncounted_reminder",
        "name": "Kits Still to Count",
        "category": "Inventory",
        "description": "Internal ping (daily job): a session ended over a day ago and its kits still haven't been counted back in — nudges the assigned instructors.",
        "subject": "Kits still to count",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Your session hasn't been closed out yet — these kits still need counting: {labels}.</p>"
            "<p>You can do it from the session page in the portal.</p>"
        ),
        "placeholders": ["name", "labels"],
        "attachment_labels": [],
        "is_internal": True,
    },
    {
        "key": "overdue_item_reminder",
        "name": "Item Overdue",
        "category": "Inventory",
        "description": "Internal ping (daily job): a kit/item on loan is past its due-back date and hasn't been recorded as returned.",
        "subject": "Something is due back",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>{what} was due back on {due_back_on} and we haven't recorded it returning. "
            "If you've already handed it over, let operations know so we can fix the record.</p>"
        ),
        "placeholders": ["name", "what", "due_back_on"],
        "attachment_labels": [],
        "is_internal": True,
    },

    # ── Certificates ─────────────────────────────────────────────────────
    {
        "key": "student_completion_certificate",
        "name": "Student Workshop Certificate",
        "category": "Certificates",
        "description": "Sent when a cohort completes and a student's workshop-completion certificate is issued — PDF attached, not uploaded to storage.",
        "subject": "Your SpacePoint certificate — {program_name}",
        "body_html": (
            "<p>Hi {student_name},</p>"
            "<p>Congratulations on completing <strong>{program_name}</strong> ({dates})!</p>"
            "<p>Your certificate of completion is attached to this email as a PDF.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["student_name", "program_name", "dates"],
        "attachment_labels": ["Certificate PDF"],
        "is_internal": False,
    },
    {
        "key": "lms_certificate_ready",
        "name": "LMS Course/Path Certificate",
        "category": "Certificates",
        "description": "Sent when a student earns an LMS course or learning-path completion certificate.",
        "subject": "Your SpacePoint certificate — {what}",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Congratulations on completing the {kind} <strong>{what}</strong>!</p>"
            "<p>Your certificate is attached to this email as a PDF. You can also download it any time "
            "from your profile.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "kind", "what"],
        "attachment_labels": ["Certificate PDF"],
        "is_internal": False,
    },

    # ── Competitions ─────────────────────────────────────────────────────
    {
        "key": "competition_team_advanced",
        "name": "Team Advanced",
        "category": "Competitions",
        "description": "Sent to each member of a team when ops advances it to the next competition stage.",
        "subject": "You're through to the next stage!",
        "body_html": (
            "<p>Hi {name},</p>"
            "<p>Congratulations — <b>{team_name}</b> has advanced to <b>{to_cohort_name}</b>! "
            "Log in to see what's next on your checklist.</p>"
            "<p>— SpacePoint</p>"
        ),
        "placeholders": ["name", "team_name", "to_cohort_name"],
        "attachment_labels": [],
        "is_internal": False,
    },
]

# Tokens whose *value* is itself HTML (a link tag, a QR <img>, a multi-line
# info block) rather than plain text — these must not be HTML-escaped when
# substituted, the same exemption `{signature}` gets in
# `routers/documents.py::_fill_placeholders`. Keyed by template key; falls
# back to no exemptions for anything not listed. Note `{where}` is plain
# text in session_assignment/call_invite (so it's escaped like any other
# value) but carries real `<br>`/`<a>` tags in ticket_confirmation — same
# token name, different shape, because the two call sites build it
# differently.
STRUCTURAL_TOKENS: dict[str, set[str]] = {
    "approval_credentials": {"login_info"},
    "ticket_confirmation": {"where", "ticket_qr"},
}

assert len({t["key"] for t in EMAIL_TEMPLATE_DEFAULTS}) == len(EMAIL_TEMPLATE_DEFAULTS), "duplicate email template key"
