-- 0016 — document_templates base table.
--
-- Genuine pre-existing gap (flagged during Workstream A4's ETL work, not fixed
-- until now): this table was only ever defined via the SQLAlchemy model
-- (app/models/document_template.py), never via a numbered SQL snapshot or the
-- startup-DDL hook. Every dev/Supabase DB so far happened to already have it
-- (created ad hoc at some point in project history), so nobody hit this until
-- a truly from-scratch VPS boot. 0008/0009/0014 all ALTER or reference this
-- table and fail on a database that has never had it.

CREATE TABLE IF NOT EXISTS document_templates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key                 VARCHAR(50) NOT NULL UNIQUE,
    name                VARCHAR(255) NOT NULL,
    roles               TEXT[] NOT NULL DEFAULT '{}',
    body_text           TEXT,
    template_file_url   VARCHAR(512),
    template_file_path  VARCHAR(512),
    type                VARCHAR(20) NOT NULL DEFAULT 'letter',
    is_system           BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at          TIMESTAMPTZ DEFAULT now()
);
