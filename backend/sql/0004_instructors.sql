-- Phase 3 - instructors domain schema (+ 2 shared document tables pulled
-- forward from Phase 4: id_cards, certificates).
-- Safe to run on a fresh Supabase project after 0001-0003.
-- Note: `checklist_modules` (not bare `modules`) avoids colliding with the
-- interns domain's own `modules` table already in this schema.

-- Enums -------------------------------------------------------------------
CREATE TYPE application_status AS ENUM ('in_progress', 'under_review', 'phase_1_approved', 'approved', 'rejected');
CREATE TYPE instructor_video_status AS ENUM ('draft', 'submitted');
CREATE TYPE module_submission_status AS ENUM ('submitted', 'approved', 'rejected');
CREATE TYPE payment_letter_status AS ENUM ('draft', 'published', 'signed', 'paid');
CREATE TYPE payment_session_role AS ENUM ('Lead Facilitator', 'Facilitator', 'Assistant Facilitator');
CREATE TYPE certificate_type AS ENUM ('workshop_delivery', 'internship_completion', 'instructor_completion');

-- Invitation codes (admin-managed; distinct from users.invite_code referrals) --
CREATE TABLE IF NOT EXISTS invitation_codes (
    id         UUID PRIMARY KEY,
    code       VARCHAR(100) UNIQUE NOT NULL,
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    expires_at TIMESTAMPTZ,
    max_uses   INTEGER NOT NULL DEFAULT 20,
    used_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_invitation_codes_code ON invitation_codes(code);

-- Applicant profile (1:1 with users) -------------------------------------------
CREATE TABLE IF NOT EXISTS applicant_profiles (
    user_id                  UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    university                VARCHAR(255),
    highest_degree            VARCHAR(100),
    highest_degree_other      VARCHAR(255),
    city_of_residence         VARCHAR(100),
    deliver_cities            TEXT[],
    background_areas          TEXT[],
    background_other          VARCHAR(255),
    has_own_transportation    BOOLEAN NOT NULL DEFAULT FALSE,
    country                   VARCHAR(100) NOT NULL DEFAULT 'United Arab Emirates',
    referred_by_ambassador_id UUID REFERENCES users(id) ON DELETE SET NULL  -- ambassador-referral hook (PLAN §9.2)
);

-- Application review state machine (instructors/HANDOFF.md §4) ----------------
CREATE TABLE IF NOT EXISTS application_reviews (
    id          UUID PRIMARY KEY,
    user_id     UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status      application_status NOT NULL DEFAULT 'in_progress',
    admin_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    feedback    TEXT,
    reviewed_at TIMESTAMPTZ
);

-- Phase 1: 3 video summaries per applicant -------------------------------------
CREATE TABLE IF NOT EXISTS video_submissions (
    id            UUID PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    video_no      INTEGER NOT NULL,
    youtube_url   TEXT,
    summary_text  TEXT,
    word_count    INTEGER NOT NULL DEFAULT 0,
    status        instructor_video_status NOT NULL DEFAULT 'draft',
    submitted_at  TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_video_submissions_user ON video_submissions(user_id);

-- Phase 2: one presentation link per applicant ---------------------------------
CREATE TABLE IF NOT EXISTS presentation_submissions (
    id           UUID PRIMARY KEY,
    user_id      UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    video_link   TEXT NOT NULL,
    submitted_at TIMESTAMPTZ DEFAULT now()
);

-- Phase 1 curriculum: checklist_modules -> module_sections -> checklist_items --
CREATE TABLE IF NOT EXISTS checklist_modules (
    id         UUID PRIMARY KEY,
    title      VARCHAR(255) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS module_sections (
    id         UUID PRIMARY KEY,
    module_id  UUID NOT NULL REFERENCES checklist_modules(id) ON DELETE CASCADE,
    title      VARCHAR(255) NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS checklist_items (
    id          UUID PRIMARY KEY,
    module_id   UUID NOT NULL REFERENCES checklist_modules(id) ON DELETE CASCADE,
    section_id  UUID REFERENCES module_sections(id) ON DELETE CASCADE,
    item_code   VARCHAR(50) NOT NULL,
    title       VARCHAR(255) NOT NULL,
    description TEXT,
    sort_order  INTEGER NOT NULL DEFAULT 1,
    is_required BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS user_checklist_progress (
    id                UUID PRIMARY KEY,
    user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    checklist_item_id UUID NOT NULL REFERENCES checklist_items(id) ON DELETE CASCADE,
    is_completed      BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_user_checklist_progress_user ON user_checklist_progress(user_id);

-- The actual Phase-1 PDF upload + admin review row, one per (user, module) ----
CREATE TABLE IF NOT EXISTS module_submissions (
    id                 UUID PRIMARY KEY,
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    module_id          UUID NOT NULL REFERENCES checklist_modules(id) ON DELETE CASCADE,
    file_url           TEXT NOT NULL,
    original_filename  VARCHAR(255),
    notes_text         TEXT,
    status             module_submission_status NOT NULL DEFAULT 'submitted',
    feedback           TEXT,
    submitted_at       TIMESTAMPTZ DEFAULT now(),
    reviewed_at        TIMESTAMPTZ,
    reviewer_admin_id  UUID REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_module_submissions_user ON module_submissions(user_id);

-- Instructor profile — card fields live solely in the shared id_cards table ---
CREATE TABLE IF NOT EXISTS instructor_profiles (
    user_id             UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    linkedin_url        TEXT,
    photo_url           TEXT,
    contract_url        TEXT,
    signed_contract_url TEXT,
    created_at          TIMESTAMPTZ DEFAULT now(),
    updated_at          TIMESTAMPTZ DEFAULT now()
);

-- Personal document vault ------------------------------------------------------
CREATE TABLE IF NOT EXISTS instructor_documents (
    id            UUID PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_type VARCHAR(100) NOT NULL,
    file_url      TEXT NOT NULL,
    uploaded_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_instructor_documents_user ON instructor_documents(user_id);

-- Training (facilitator-managed content, instructor-consumed) -----------------
CREATE TABLE IF NOT EXISTS training_modules (
    id         UUID PRIMARY KEY,
    title      VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    sort_order INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS training_videos (
    id          UUID PRIMARY KEY,
    module_id   UUID NOT NULL REFERENCES training_modules(id) ON DELETE CASCADE,
    title       VARCHAR(255) NOT NULL,
    description TEXT,
    notes       TEXT,
    video_path  TEXT NOT NULL,  -- Supabase Storage path, private bucket — stream via signed URL
    sort_order  INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_training_progress (
    id           UUID PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    video_id     UUID NOT NULL REFERENCES training_videos(id) ON DELETE CASCADE,
    is_completed BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_user_training_progress_user ON user_training_progress(user_id);
CREATE INDEX IF NOT EXISTS idx_user_training_progress_video ON user_training_progress(video_id);

-- Library (facilitator-managed content, instructor-consumed) ------------------
CREATE TABLE IF NOT EXISTS library_modules (
    id          UUID PRIMARY KEY,
    name        VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS library_resources (
    id          UUID PRIMARY KEY,
    title       VARCHAR(255) NOT NULL,
    description TEXT,
    format      VARCHAR(20) NOT NULL,
    file_url    TEXT NOT NULL,
    uploader_id UUID REFERENCES users(id) ON DELETE SET NULL,
    module_id   UUID NOT NULL REFERENCES library_modules(id) ON DELETE CASCADE,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Payments ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payment_batches (
    id                 UUID PRIMARY KEY,
    name               VARCHAR(255) NOT NULL,
    description        TEXT,
    created_by_admin_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at         TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payment_letters (
    id                       UUID PRIMARY KEY,
    batch_id                 UUID REFERENCES payment_batches(id) ON DELETE SET NULL,
    instructor_user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    letter_date              VARCHAR(50),
    reference                VARCHAR(255) NOT NULL DEFAULT 'Facilitator Agreement',
    status                   payment_letter_status NOT NULL DEFAULT 'draft',
    is_published             BOOLEAN NOT NULL DEFAULT FALSE,
    pdf_url                  TEXT,
    signed_pdf_url           TEXT,
    instructor_signature_data TEXT,  -- base64 PNG, re-embedded into the PDF on each sign
    signed_at                TIMESTAMPTZ,
    admin_notes              TEXT,
    created_at               TIMESTAMPTZ DEFAULT now(),
    updated_at               TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payment_letters_instructor ON payment_letters(instructor_user_id);

CREATE TABLE IF NOT EXISTS payment_sessions (
    id                  UUID PRIMARY KEY,
    payment_letter_id    UUID NOT NULL REFERENCES payment_letters(id) ON DELETE CASCADE,
    session_date         VARCHAR(50),
    workshop_description VARCHAR(255) NOT NULL,
    role                 payment_session_role NOT NULL,
    location             VARCHAR(255),
    duration_hours       FLOAT,
    compensation_aed     FLOAT NOT NULL DEFAULT 0,
    sort_order           INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_payment_sessions_letter ON payment_sessions(payment_letter_id);

CREATE TABLE IF NOT EXISTS payment_addons (
    id                UUID PRIMARY KEY,
    payment_letter_id UUID NOT NULL REFERENCES payment_letters(id) ON DELETE CASCADE,
    description       VARCHAR(255) NOT NULL,
    amount_aed        FLOAT NOT NULL DEFAULT 0,
    notes             VARCHAR(255),
    sort_order        INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_payment_addons_letter ON payment_addons(payment_letter_id);

CREATE TABLE IF NOT EXISTS instructor_bank_details (
    id                  UUID PRIMARY KEY,
    user_id              UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    account_holder_name  VARCHAR(255),
    bank_name            VARCHAR(255),
    iban                 VARCHAR(50),
    swift_bic            VARCHAR(20),
    updated_at           TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS portal_settings (
    id         UUID PRIMARY KEY,
    key        VARCHAR(100) UNIQUE NOT NULL,
    value      TEXT,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Shared document tables (PLAN §4.5) — pulled forward from Phase 4 because the
-- instructor portal's Profile Card page needs id_card.py now -----------------
CREATE TABLE IF NOT EXISTS id_cards (
    id           UUID PRIMARY KEY,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         user_role NOT NULL,
    card_id      VARCHAR(50),    -- e.g. SP-INS-0012
    front_url    TEXT,
    back_url     TEXT,
    pdf_url      TEXT,
    generated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_id_cards_user ON id_cards(user_id);

-- Unified certificates table — `type` discriminator lets workshop-delivery
-- certs (Phase 3, payment_session_id set) and completion certs (Phase 4,
-- payment_session_id null) share one table instead of colliding on the name.
CREATE TABLE IF NOT EXISTS certificates (
    id                 UUID PRIMARY KEY,
    user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type               certificate_type NOT NULL,
    file_url           TEXT NOT NULL,
    generated_at       TIMESTAMPTZ DEFAULT now(),
    generated_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    payment_session_id UUID REFERENCES payment_sessions(id) ON DELETE SET NULL,
    workshop_name      VARCHAR(255),
    workshop_date      VARCHAR(50),
    location           VARCHAR(255)
);
CREATE INDEX IF NOT EXISTS idx_certificates_user ON certificates(user_id);
