-- Fixes a pre-existing schema drift discovered while building the A4 legacy
-- ETL (backend/scripts/migrate_legacy.py): LibraryResource.resource_type
-- (models/instructors/library.py) has never had a matching SQL snapshot or
-- startup-DDL entry, so any freshly-provisioned DB (not just an ETL target)
-- would 500 the first time a library resource is read/written.
--
-- Safe to run more than once.

ALTER TABLE library_resources ADD COLUMN IF NOT EXISTS resource_type VARCHAR(10) NOT NULL DEFAULT 'file';
