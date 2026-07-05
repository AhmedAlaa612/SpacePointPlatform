from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import admin, auth, documents, notifications
from app.routers.apply import router as apply_router
from app.routers.interns import admin as interns_admin
from app.routers.interns import intern as interns_intern
from app.routers.interns import leader as interns_leader
from app.routers.interns import shared as interns_shared
from app.routers.ambassadors import router as ambassadors_router
from app.routers.instructors import router as instructors_router


async def _run_startup_migrations() -> None:
    """Idempotent schema reconciliation.

    The project provisions a fresh Supabase via the SQL artifacts in
    backend/sql/; this hook only adds tables/columns that landed after those
    snapshots, using IF NOT EXISTS so it is safe to run on every boot. It is
    deliberately NON-destructive — legacy-table removal lives in the one-shot
    backend/sql/0007_cleanup_legacy.sql, not here.
    """
    from sqlalchemy import text
    from app.db.session import engine

    async with engine.begin() as conn:
        # ── document_requests (shared) — keep in sync with models/document_request.py ──
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_requests (
                id              UUID PRIMARY KEY,
                user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                type            VARCHAR(50) NOT NULL,
                status          VARCHAR(50) NOT NULL DEFAULT 'pending',
                requested_role  VARCHAR(50),
                notes           TEXT,
                admin_notes     TEXT,
                file_url        TEXT,
                created_at      TIMESTAMPTZ DEFAULT now(),
                updated_at      TIMESTAMPTZ DEFAULT now()
            );
        """))
        # columns added after 0006 — backfill on pre-existing tables
        await conn.execute(text("ALTER TABLE document_requests ADD COLUMN IF NOT EXISTS requested_role VARCHAR(50);"))
        await conn.execute(text("ALTER TABLE document_requests ADD COLUMN IF NOT EXISTS file_url TEXT;"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_document_requests_user_id ON document_requests(user_id);"))

        # ── unified generated documents (letters) — replaces recommendation_letters
        #    + intern_letters; certificates keep their own first-class table ──
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS documents (
                id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                template_id   UUID REFERENCES document_templates(id) ON DELETE SET NULL,
                label         VARCHAR(255) NOT NULL,
                file_url      TEXT NOT NULL,
                generated_by  UUID REFERENCES users(id) ON DELETE SET NULL,
                data          JSONB NOT NULL DEFAULT '{}',
                generated_at  TIMESTAMPTZ DEFAULT now()
            );
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_documents_user ON documents(user_id);"))

        # profile photo + LinkedIn live on users (shared across every role)
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_url TEXT;"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS linkedin_url TEXT;"))

        # ── unified applications inbox (all public applications, admin-reviewed) ──
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS applications (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                role            VARCHAR(50) NOT NULL,
                status          VARCHAR(20) NOT NULL DEFAULT 'pending',
                full_name       VARCHAR(255) NOT NULL,
                email           VARCHAR(255) NOT NULL,
                phone           VARCHAR(50),
                country         VARCHAR(100),
                password_hash   TEXT NOT NULL,
                invite_code     VARCHAR(50),
                invited_by_id   UUID REFERENCES users(id) ON DELETE SET NULL,
                cv_url          TEXT,
                answers         JSONB NOT NULL DEFAULT '{}',
                admin_notes     TEXT,
                reviewed_by     UUID REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at     TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT now()
            );
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_applications_role_status ON applications(role, status);"))

        # ── admin-configurable per-role application questions (shown on /apply/{role}) ──
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS apply_questions (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                audience        VARCHAR(50) NOT NULL,
                question_text   TEXT NOT NULL,
                question_type   VARCHAR(20) NOT NULL DEFAULT 'text',
                required        BOOLEAN NOT NULL DEFAULT TRUE,
                options         JSONB NOT NULL DEFAULT '[]',
                sort_order      INTEGER NOT NULL DEFAULT 0,
                is_active       BOOLEAN NOT NULL DEFAULT TRUE,
                created_at      TIMESTAMPTZ DEFAULT now()
            );
        """))
        await conn.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_apply_questions_audience ON apply_questions(audience) WHERE is_active;"
        ))

        # ── document templates: explicit render type + system flag (replaces the
        #    old "guess the type from substrings in the key" behaviour) ──
        await conn.execute(text(
            "ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS type VARCHAR(20) NOT NULL DEFAULT 'letter';"
        ))
        await conn.execute(text(
            "ALTER TABLE document_templates ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT FALSE;"
        ))
        # backfill anything that already behaves like a certificate (has a base image, or a cert-ish key)
        await conn.execute(text("""
            UPDATE document_templates SET type = 'certificate'
             WHERE type <> 'certificate' AND (template_file_url IS NOT NULL OR key ILIKE '%certificate%');
        """))
        # seed the workshop-delivery cert as an editable, non-deletable system template
        # (its text used to be hardcoded in services/documents/certificate.py)
        existing_wd = (await conn.execute(
            text("SELECT 1 FROM document_templates WHERE key = 'workshop_delivery' LIMIT 1")
        )).first()
        if existing_wd is None:
            await conn.execute(text("""
                INSERT INTO document_templates (id, key, name, type, is_system, roles, body_text)
                VALUES (
                    gen_random_uuid(), 'workshop_delivery', 'Workshop Facilitation Certificate',
                    'certificate', TRUE, ARRAY[]::varchar[],
                    'in recognition of his/her outstanding contribution as a facilitator to the <b>{workshop_name}</b>, delivered on <b>{workshop_date}</b> at <b>{location}</b>'
                );
            """))

        # ── ID cards: one shared number per PERSON (SP-XXXX-UAE), not per role.
        #    Legacy per-role sequences (card_seq_admin, card_seq_intern, …) are
        #    left in place (harmless, unused) rather than dropped. ──
        await conn.execute(text("CREATE SEQUENCE IF NOT EXISTS card_seq_person START 1 INCREMENT 1"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS card_number INTEGER;"))
        await conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_card_number "
            "ON users(card_number) WHERE card_number IS NOT NULL;"
        ))
        # Backfill: any user with pre-existing per-role id_cards but no card_number
        # yet gets a fresh sequential number (old per-role numbers came from 8
        # independent sequences, so e.g. "instructor #1" and "facilitator #1"
        # are different people — the old numbers can't be reused as-is without
        # colliding). Order by earliest card generation so longtime users keep
        # lower numbers.
        await conn.execute(text("""
            WITH distinct_users AS (
                SELECT user_id, MIN(generated_at) AS first_gen
                FROM id_cards
                WHERE card_id IS NOT NULL
                GROUP BY user_id
            ),
            ranked AS (
                SELECT user_id, ROW_NUMBER() OVER (ORDER BY first_gen) AS rn
                FROM distinct_users
            )
            UPDATE users u
            SET card_number = ranked.rn
            FROM ranked
            WHERE u.id = ranked.user_id AND u.card_number IS NULL;
        """))
        # Rewrite every existing id_cards row to the person's shared number/format
        # (idempotent — only touches rows that don't already match).
        await conn.execute(text("""
            UPDATE id_cards ic
            SET card_id = 'SP-' || lpad(u.card_number::text, 4, '0') || '-UAE'
            FROM users u
            WHERE ic.user_id = u.id AND u.card_number IS NOT NULL
              AND ic.card_id IS DISTINCT FROM ('SP-' || lpad(u.card_number::text, 4, '0') || '-UAE');
        """))
        # Keep the sequence ahead of any backfilled number so new allocations
        # never collide with one just assigned above.
        await conn.execute(text("""
            DO $$
            DECLARE
                max_num INTEGER;
                cur_val BIGINT;
            BEGIN
                SELECT COALESCE(MAX(card_number), 0) INTO max_num FROM users;
                SELECT last_value INTO cur_val FROM card_seq_person;
                IF max_num > cur_val THEN
                    PERFORM setval('card_seq_person', max_num);
                END IF;
            END $$;
        """))

        # ── Pivot Phase 6: contract signing (mirrors payment-letter signing).
        #    No separate status enum — signed state is derived from
        #    signed_contract_url/contract_signed_at, since contracts have no
        #    admin draft/publish step (unlike payment letters). ──
        await conn.execute(text("ALTER TABLE instructor_profiles ADD COLUMN IF NOT EXISTS contract_signature_data TEXT;"))
        await conn.execute(text("ALTER TABLE instructor_profiles ADD COLUMN IF NOT EXISTS contract_signed_at TIMESTAMPTZ;"))

    # ── Phase-2 "research approved" applicant stage (parity with the live VPS
    #    pipeline, whose application_reviews already carries RESEARCH_APPROVED).
    #    ALTER TYPE ADD VALUE must not share a transaction with any use of the new
    #    value, so run it on a dedicated AUTOCOMMIT connection and tolerate the
    #    "already exists" race. ──
    autocommit_engine = engine.execution_options(isolation_level="AUTOCOMMIT")
    try:
        async with autocommit_engine.connect() as conn:
            await conn.execute(
                text("ALTER TYPE application_status ADD VALUE IF NOT EXISTS 'research_approved'")
            )
    except Exception as e:  # noqa: BLE001 — best-effort idempotent DDL
        print(f"[startup] research_approved enum add skipped: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _run_startup_migrations()
    yield


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(apply_router)          # public: /apply/*
app.include_router(notifications.router)  # shared: /notifications/*
app.include_router(documents.router)  # shared: /documents/*  (Phase 4)
app.include_router(admin.router, prefix="/admin")  # shared: /admin/users/*  (generic user management)

# Interns domain (Phase 1) — /interns/*
app.include_router(interns_admin.router, prefix="/interns")
app.include_router(interns_leader.router, prefix="/interns")
app.include_router(interns_intern.router, prefix="/interns")
app.include_router(interns_shared.router, prefix="/interns")

# Ambassadors domain (Phase 2) — /ambassadors/*
app.include_router(ambassadors_router, prefix="/ambassadors")

# Instructors domain (Phase 3) — /instructors/*  (public apply endpoint lives
# in routers/auth.py — /auth/instructor-apply — matching the existing
# instructor pipeline convention, not a separate /apply/* router)
app.include_router(instructors_router, prefix="/instructors")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": settings.PROJECT_NAME}
