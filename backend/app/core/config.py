from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "SpacePoint Unified Platform"

    # Structured logging (app/core/log_context.py)
    LOG_LEVEL: str = "INFO"

    # Database — async driver, e.g.
    # postgresql+asyncpg://postgres:postgres@host:5432/postgres
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/spacepoint"
    # Dedicated test database — pytest fixtures use this, never DATABASE_URL.
    DATABASE_URL_TEST: str = ""

    # Background job queue (V2 R2-1) — ARQ + Redis, bound to 127.0.0.1 only in prod.
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_URL_TEST: str = ""

    # JWT auth
    SECRET_KEY: str = "supersecretkey-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 12 * 60  # 12 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Supabase Storage (server-side service role key)
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

    # Stripe Checkout — LMS course purchases (Stage S, August Build Brief
    # Branch 4). Webhook secret is a separate value from the CLI's own
    # `stripe listen` secret when testing locally.
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Intercom identity verification (Fin support messenger on /learn/*).
    # HMAC-SHA256 key for the `user_hash` the Messenger boots with, so a
    # student cannot open a chat as someone else. Server-side only — the
    # workspace App ID is a separate, *public* value that lives in the
    # frontend build (VITE_INTERCOM_APP_ID) and is deliberately not
    # mirrored here. Blank disables identity: /lms/support/chat-identity
    # returns 503 rather than serving an unverified payload.
    INTERCOM_IDENTITY_SECRET: str = ""

    # Storage backend (Phase 7 / GO_LIVE §3.A3)
    # - "supabase": Supabase Storage buckets (dev default, pre-cutover)
    # - "local":    files under STORAGE_ROOT/{bucket}/{path}, Fernet-encrypted at
    #               rest, served via GET /files/{bucket}/{path} with HMAC-signed URLs
    STORAGE_BACKEND: str = "supabase"
    STORAGE_ROOT: str = "./storage"
    # Fernet key (32-byte urlsafe base64) — REQUIRED when STORAGE_BACKEND=local.
    # Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Losing this key means losing every stored file — back it up offline.
    STORAGE_ENCRYPTION_KEY: str = ""

    # Cloudflare R2 (S3-compatible). Only read when a backend resolves to "r2";
    # leaving these blank is what keeps every other deployment unaffected.
    # One R2 bucket holds everything — the app's own "bucket" names become key
    # prefixes inside it (see services/storage_r2.py), so an R2 key looks like
    # "lms-hls/{video_id}/segment_000.ts".
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = ""
    # Defaults to https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com when blank —
    # set explicitly only to pin a jurisdiction-specific endpoint.
    R2_ENDPOINT_URL: str = ""

    # Per-domain storage override for video bytes specifically. Blank (the
    # default) means "follow STORAGE_BACKEND", i.e. no behaviour change at all.
    #
    # This exists because video is the only thing under real load: 400
    # concurrent students pulling HLS segments through the API is ~1 Gbps and
    # a Fernet decrypt per segment on a 4-vCPU box. Moving *just* video to R2
    # fixes that without also relocating payment letters, signed contracts,
    # certificates and every document bucket in the same change.
    #
    # It is also the rollback lever: because storage paths are identical across
    # backends, flipping this back to "" re-serves the pre-existing local HLS
    # tree from the same DB rows, with no migration to unwind.
    VIDEO_STORAGE_BACKEND: str = ""

    # SMTP
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""  # e.g. "SpacePoint <noreply@spacepoint.ae>"

    # App
    BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:5173"
    ADMIN_EMAIL: str = "admin@spacepoint.local"
    ADMIN_PASSWORD: str = "changeme"
    DEFAULT_SIGNATORY_NAME: str = "ABDULLAH ALSALMANI"
    DEFAULT_SIGNATORY_TITLE: str = "Co-Founder & CEO of SpacePoint"

    # CORS — comma-separated list of allowed origins
    CORS_ORIGINS: str = "http://localhost:5173"
    # Separate allowlist for public, unauthenticated form endpoints (V2 R1-5) —
    # the marketing site (spacepoint.ae) needs to POST here from the browser,
    # a different origin than the portal frontend above.
    PUBLIC_FORM_ORIGINS: str = ""

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def public_form_origins(self) -> list[str]:
        return [o.strip() for o in self.PUBLIC_FORM_ORIGINS.split(",") if o.strip()]


settings = Settings()
