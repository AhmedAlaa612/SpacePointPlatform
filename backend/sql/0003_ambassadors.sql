-- Phase 2 - ambassadors domain schema
-- Safe to run on a fresh Supabase project after 0002_interns.sql.

-- Ensure users table has the recruit_points_awarded column
ALTER TABLE users ADD COLUMN IF NOT EXISTS recruit_points_awarded BOOLEAN NOT NULL DEFAULT FALSE;

-- Leads -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS leads (
    id            UUID PRIMARY KEY,
    ambassador_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contact_name  VARCHAR(255) NOT NULL,
    company       VARCHAR(255),                              -- B2B only; null for B2C individuals
    type          VARCHAR(50)  NOT NULL,                      -- B2B, distributor
    status        VARCHAR(50)  NOT NULL DEFAULT 'submitted',  -- submitted, in review, converted, closed
    notes         TEXT,
    points_awarded BOOLEAN NOT NULL DEFAULT FALSE,            -- conversion points awarded once
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_leads_ambassador ON leads(ambassador_id);

-- Lead comments (ambassador ↔ admin thread on a lead) -------------------------
CREATE TABLE IF NOT EXISTS lead_comments (
    id         UUID PRIMARY KEY,
    lead_id    UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    author_id  UUID REFERENCES users(id) ON DELETE SET NULL,
    body       TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_lead_comments_lead ON lead_comments(lead_id);

-- Ambassador Tasks (renamed from tasks to avoid collision with interns.tasks) --
CREATE TABLE IF NOT EXISTS ambassador_tasks (
    id            UUID PRIMARY KEY,
    assigned_to   UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_by    UUID REFERENCES users(id) ON DELETE SET NULL,
    title         VARCHAR(255) NOT NULL,
    description   TEXT,
    deadline      TIMESTAMPTZ,
    status        VARCHAR(50)  NOT NULL DEFAULT 'pending',    -- pending, accepted, submitted, approved, rejected, edit_requested
    points_reward INTEGER NOT NULL DEFAULT 0,
    edit_notes    TEXT,
    submission    TEXT,                                      -- ambassador's submitted work (link / notes)
    points_awarded BOOLEAN NOT NULL DEFAULT FALSE,           -- reward currently held (reversed on revoke)
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ambassador_tasks_assigned ON ambassador_tasks(assigned_to);

-- Teacher sessions ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS teacher_sessions (
    id                UUID PRIMARY KEY,
    teacher_id        UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title             VARCHAR(255) NOT NULL,
    description       TEXT,
    date              TIMESTAMPTZ NOT NULL,
    status            VARCHAR(50)  NOT NULL DEFAULT 'pending',  -- pending, approved, done, rejected, cancelled
    status_note       TEXT,                                     -- reason given on cancel / reject
    material_sent     BOOLEAN NOT NULL DEFAULT FALSE,
    material_link     TEXT,
    planned_students  INTEGER NOT NULL DEFAULT 0,
    attended_students INTEGER NOT NULL DEFAULT 0,
    points_awarded    BOOLEAN NOT NULL DEFAULT FALSE,           -- delivery points currently held
    created_at        TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_sessions_teacher ON teacher_sessions(teacher_id);

-- Points ledger (lifetime — only ever accrues, never decreases) ---------------
CREATE TABLE IF NOT EXISTS points_transactions (
    id            UUID PRIMARY KEY,
    ambassador_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount        INTEGER NOT NULL,
    type          VARCHAR(50) NOT NULL DEFAULT 'earn',         -- always 'earn'
    reason        TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_points_ambassador ON points_transactions(ambassador_id);

-- Titles (admin-configurable ranks unlocked by lifetime points) ---------------
CREATE TABLE IF NOT EXISTS titles (
    id          UUID PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    min_points  INTEGER NOT NULL DEFAULT 0,
    icon        VARCHAR(50),
    color       VARCHAR(20),
    sort_order  INTEGER NOT NULL DEFAULT 0,
    audience    VARCHAR(20) NOT NULL DEFAULT 'ambassador',     -- ambassador | teacher
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Achievements (earned milestone badges, distinct from titles) ----------------
CREATE TABLE IF NOT EXISTS achievements (
    id            UUID PRIMARY KEY,
    ambassador_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code          VARCHAR(50) NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now(),
    CONSTRAINT uq_achievement_per_user UNIQUE (ambassador_id, code)
);

-- Badge definitions (admin-configurable milestone badges) ---------------------
CREATE TABLE IF NOT EXISTS badge_definitions (
    id            UUID PRIMARY KEY,
    code          VARCHAR(50) UNIQUE NOT NULL,
    label         VARCHAR(100) NOT NULL,
    description   VARCHAR(255),
    icon          VARCHAR(50),
    criteria_type VARCHAR(50) NOT NULL,   -- converted_leads, active_teachers, sessions_done, students_reached, lifetime_points
    threshold     INTEGER NOT NULL DEFAULT 1,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    audience      VARCHAR(20) NOT NULL DEFAULT 'ambassador',  -- ambassador | teacher
    created_at    TIMESTAMPTZ DEFAULT now()
);

-- Materials library (shared teaching resources) -------------------------------
CREATE TABLE IF NOT EXISTS materials (
    id          UUID PRIMARY KEY,
    created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    title       VARCHAR(255) NOT NULL,
    description TEXT,
    link        TEXT NOT NULL,
    category    VARCHAR(100),
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Application questions (admin-configurable teacher application form) ---------
CREATE TABLE IF NOT EXISTS application_questions (
    id            UUID PRIMARY KEY,
    question_text VARCHAR(500) NOT NULL,
    question_type VARCHAR(50)  NOT NULL,                        -- text, number, radio, multiple_choice
    required      BOOLEAN NOT NULL DEFAULT TRUE,
    "order"       INTEGER NOT NULL DEFAULT 0,
    options       TEXT[],                                        -- choices for radio / multiple_choice
    created_at    TIMESTAMPTZ DEFAULT now(),
    deleted_at    TIMESTAMPTZ                                    -- soft-delete; NULL = active
);
CREATE INDEX IF NOT EXISTS idx_application_questions_deleted ON application_questions(deleted_at);

-- Teacher applications (pending teacher sign-ups via the invite form) ---------
CREATE TABLE IF NOT EXISTS teacher_applications (
    id            UUID PRIMARY KEY,
    full_name     VARCHAR(255) NOT NULL,
    email         VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    invite_code   VARCHAR(100) NOT NULL,
    invited_by_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    answers       JSONB DEFAULT '{}',                           -- { question_id: answer_value }
    status        VARCHAR(50)  NOT NULL DEFAULT 'pending',      -- pending, approved, rejected
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_teacher_applications_status     ON teacher_applications(status);
CREATE INDEX IF NOT EXISTS idx_teacher_applications_invited_by ON teacher_applications(invited_by_id);

-- System settings (points reward amounts, etc.) ------------------------------
CREATE TABLE IF NOT EXISTS system_settings (
    key   VARCHAR(255) PRIMARY KEY,
    value VARCHAR(255) NOT NULL
);

-- ── Seed data ───────────────────────────────────────────────────────────────

-- Reward amounts
INSERT INTO system_settings (key, value) VALUES
    ('lead_points_reward', '1000'),
    ('teacher_points_reward', '500'),
    ('instructor_points_reward', '500'),
    ('session_points_reward', '200')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;

-- Default title ladder (edit freely in the Admin → Titles panel)
INSERT INTO titles (id, name, min_points, icon, color, sort_order, audience) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'Cadet',      0,     'Rocket',  '#9ca3af', 1, 'ambassador'),
    ('a0000000-0000-0000-0000-000000000002', 'Pilot',      1000,  'Star',    '#60a5fa', 2, 'ambassador'),
    ('a0000000-0000-0000-0000-000000000003', 'Navigator',  3000,  'Satellite', '#a880ff', 3, 'ambassador'),
    ('a0000000-0000-0000-0000-000000000004', 'Commander',  7000,  'Shield',  '#643f83', 4, 'ambassador'),
    ('a0000000-0000-0000-0000-000000000005', 'Captain',    15000, 'Medal',   '#f5b942', 5, 'ambassador'),
    ('a0000000-0000-0000-0000-000000000006', 'Admiral',    30000, 'Crown',   '#facc15', 6, 'ambassador')
ON CONFLICT (id) DO NOTHING;

-- Default milestone badges (edit freely in Admin → Badges)
INSERT INTO badge_definitions (id, code, label, description, icon, criteria_type, threshold, sort_order, audience) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'first_lead',       'First Contact',   'Converted your first lead',              'Handshake',      'converted_leads',  1,   1, 'ambassador'),
    ('b0000000-0000-0000-0000-000000000002', 'ten_leads',        'Dealmaker',       'Converted 10 leads',                     'Briefcase',      'converted_leads',  10,  2, 'ambassador'),
    ('b0000000-0000-0000-0000-000000000003', 'first_teacher',    'Mentor',          'Recruited your first teacher',           'GraduationCap',  'active_teachers',  1,   3, 'ambassador'),
    ('b0000000-0000-0000-0000-000000000004', 'five_teachers',    'Network Builder', 'Recruited 5 active teachers',            'Users',          'active_teachers',  5,   4, 'ambassador'),
    ('b0000000-0000-0000-0000-000000000005', 'first_session',    'Liftoff',         'Your network delivered its first session','Rocket',        'sessions_done',    1,   5, 'ambassador'),
    ('b0000000-0000-0000-0000-000000000006', 'ten_sessions',     'Mission Control', '10 sessions delivered by your network',  'Radio',          'sessions_done',    10,  6, 'ambassador'),
    ('b0000000-0000-0000-0000-000000000007', 'hundred_students', 'Star Reach',      'Reached 100 students',                   'Star',           'students_reached', 100, 7, 'ambassador')
ON CONFLICT (code) DO NOTHING;

-- Default teacher title ladder (teachers earn points on session delivery)
INSERT INTO titles (id, name, min_points, icon, color, sort_order, audience) VALUES
    ('a0000000-0000-0000-0000-000000000011', 'Explorer',   0,    'Rocket', '#9ca3af', 1, 'teacher'),
    ('a0000000-0000-0000-0000-000000000012', 'Educator',   600,  'Star',   '#60a5fa', 2, 'teacher'),
    ('a0000000-0000-0000-0000-000000000013', 'Inspirer',   2000, 'Flame',  '#a880ff', 3, 'teacher'),
    ('a0000000-0000-0000-0000-000000000014', 'Luminary',   5000, 'Crown',  '#facc15', 4, 'teacher')
ON CONFLICT (id) DO NOTHING;

-- Default teacher badges (own sessions/students, not a network's)
INSERT INTO badge_definitions (id, code, label, description, icon, criteria_type, threshold, sort_order, audience) VALUES
    ('b0000000-0000-0000-0000-000000000011', 't_first_session',    'First Flight',  'Delivered your first session',  'Rocket', 'sessions_done',    1,   1, 'teacher'),
    ('b0000000-0000-0000-0000-000000000012', 't_ten_sessions',     'Seasoned',      'Delivered 10 sessions',         'Medal',  'sessions_done',    10,  2, 'teacher'),
    ('b0000000-0000-0000-0000-000000000013', 't_hundred_students', 'Classroom Hero','Reached 100 students',          'Users',  'students_reached', 100, 3, 'teacher'),
    ('b0000000-0000-0000-0000-000000000014', 't_five_hundred',     'Star Teacher',  'Reached 500 students',          'Star',   'students_reached', 500, 4, 'teacher')
ON CONFLICT (code) DO NOTHING;
