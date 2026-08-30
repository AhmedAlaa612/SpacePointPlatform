-- Runs once, on the very first boot of the `db` service in docker-compose.dev.yml
-- (Postgres only executes /docker-entrypoint-initdb.d/* when its data directory is
-- empty — so editing this file has no effect on an existing volume; you have to
-- `docker compose down -v` to make it run again).
--
-- Creates the two databases the project needs and enables pgcrypto on both.
-- pgcrypto has to exist before `alembic upgrade head`: the first migration uses
-- it, and creating an extension requires superuser — which is exactly what the
-- entrypoint runs as, and why doing it here is easier than doing it by hand.
--
-- Two databases, not one, because the test suite needs a database you can afford
-- to throw away: `alembic downgrade` is banned in this repo (two revisions drop
-- ~20 tables), so recovering from a migration you got wrong means dropping the
-- database and recreating it. That must never be the database holding your
-- seeded admin and your hand-made test teams.

CREATE DATABASE spacepoint_test;

\connect spacepoint_dev
CREATE EXTENSION IF NOT EXISTS pgcrypto;

\connect spacepoint_test
CREATE EXTENSION IF NOT EXISTS pgcrypto;
