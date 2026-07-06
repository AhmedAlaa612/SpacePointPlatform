from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "SpacePoint Unified Platform"

    # Database — async driver, e.g.
    # postgresql+asyncpg://postgres:postgres@host:5432/postgres
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/spacepoint"

    # JWT auth
    SECRET_KEY: str = "supersecretkey-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 12 * 60  # 12 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Supabase Storage (server-side service role key)
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""

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

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
