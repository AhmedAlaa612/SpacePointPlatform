-- Phase 1 - interns domain schema (generated from SQLAlchemy models)
-- Mirrors app/models/interns/* + the shared notifications table.
-- Safe to run on a fresh Supabase project after 0001_initial_users.sql.

DO $$ BEGIN CREATE TYPE work_status AS ENUM ('todo','in_progress','done'); EXCEPTION WHEN duplicate_object THEN null; END $$;
DO $$ BEGIN CREATE TYPE submission_status AS ENUM ('submitted','reviewed'); EXCEPTION WHEN duplicate_object THEN null; END $$;

CREATE TABLE IF NOT EXISTS notifications (
	id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	body TEXT, 
	type VARCHAR(50), 
	is_read BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS projects (
	id UUID NOT NULL, 
	title VARCHAR NOT NULL, 
	description TEXT, 
	status VARCHAR DEFAULT 'active' NOT NULL, 
	created_by UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS teams (
	id UUID NOT NULL, 
	name VARCHAR NOT NULL, 
	leader_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(leader_id) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS epics (
	id UUID NOT NULL, 
	project_id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	title VARCHAR NOT NULL, 
	description TEXT, 
	status work_status NOT NULL, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS project_teams (
	project_id UUID NOT NULL, 
	team_id UUID NOT NULL, 
	PRIMARY KEY (project_id, team_id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(team_id) REFERENCES teams (id)
);
CREATE TABLE IF NOT EXISTS team_members (
	team_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	PRIMARY KEY (team_id, user_id), 
	FOREIGN KEY(team_id) REFERENCES teams (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS mind_map_layouts (
	id UUID NOT NULL, 
	epic_id UUID NOT NULL, 
	layout JSONB NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	UNIQUE (epic_id), 
	FOREIGN KEY(epic_id) REFERENCES epics (id)
);
CREATE TABLE IF NOT EXISTS modules (
	id UUID NOT NULL, 
	epic_id UUID NOT NULL, 
	title VARCHAR NOT NULL, 
	description TEXT, 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(epic_id) REFERENCES epics (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS proposals (
	id UUID NOT NULL, 
	epic_id UUID NOT NULL, 
	proposed_by UUID NOT NULL, 
	title VARCHAR(255) NOT NULL, 
	description TEXT, 
	status VARCHAR NOT NULL, 
	reviewed_by UUID, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(epic_id) REFERENCES epics (id), 
	FOREIGN KEY(proposed_by) REFERENCES users (id), 
	FOREIGN KEY(reviewed_by) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS tasks (
	id UUID NOT NULL, 
	module_id UUID NOT NULL, 
	title VARCHAR NOT NULL, 
	description TEXT, 
	status work_status NOT NULL, 
	due_date TIMESTAMP WITH TIME ZONE, 
	expected_time NUMERIC(6, 2), 
	actual_time NUMERIC(6, 2), 
	created_by UUID, 
	created_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(module_id) REFERENCES modules (id), 
	FOREIGN KEY(created_by) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS task_assignees (
	task_id UUID NOT NULL, 
	user_id UUID NOT NULL, 
	PRIMARY KEY (task_id, user_id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS task_mind_map_notes (
	task_id UUID NOT NULL, 
	note TEXT, 
	updated_by UUID, 
	updated_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (task_id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id), 
	FOREIGN KEY(updated_by) REFERENCES users (id)
);
CREATE TABLE IF NOT EXISTS task_submissions (
	id UUID NOT NULL, 
	task_id UUID NOT NULL, 
	submitted_by UUID NOT NULL, 
	link VARCHAR NOT NULL, 
	note TEXT, 
	status submission_status NOT NULL, 
	score INTEGER, 
	review_comment TEXT, 
	submitted_at TIMESTAMP WITH TIME ZONE, 
	reviewed_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id), 
	FOREIGN KEY(task_id) REFERENCES tasks (id), 
	FOREIGN KEY(submitted_by) REFERENCES users (id)
);
