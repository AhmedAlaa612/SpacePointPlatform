--
-- PostgreSQL database dump
--


-- Dumped from database version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.14 (Ubuntu 16.14-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--



--
-- Name: application_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.application_status AS ENUM (
    'in_progress',
    'under_review',
    'phase_1_approved',
    'research_approved',
    'approved',
    'rejected'
);


--
-- Name: certificate_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.certificate_type AS ENUM (
    'workshop_delivery',
    'internship_completion',
    'instructor_completion'
);


--
-- Name: instructor_video_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.instructor_video_status AS ENUM (
    'draft',
    'submitted'
);


--
-- Name: module_submission_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.module_submission_status AS ENUM (
    'submitted',
    'approved',
    'rejected'
);


--
-- Name: payment_letter_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.payment_letter_status AS ENUM (
    'draft',
    'published',
    'signed',
    'paid'
);


--
-- Name: payment_session_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.payment_session_role AS ENUM (
    'Lead Facilitator',
    'Facilitator',
    'Assistant Facilitator'
);


--
-- Name: submission_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.submission_status AS ENUM (
    'submitted',
    'reviewed'
);


--
-- Name: user_role; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.user_role AS ENUM (
    'admin',
    'intern',
    'leader',
    'applicant',
    'instructor',
    'facilitator',
    'ambassador',
    'teacher'
);


--
-- Name: work_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.work_status AS ENUM (
    'todo',
    'in_progress',
    'done'
);


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: achievements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.achievements (
    id uuid NOT NULL,
    ambassador_id uuid NOT NULL,
    code character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: ambassador_tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ambassador_tasks (
    id uuid NOT NULL,
    assigned_to uuid NOT NULL,
    created_by uuid,
    title character varying(255) NOT NULL,
    description text,
    deadline timestamp with time zone,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    points_reward integer DEFAULT 0 NOT NULL,
    edit_notes text,
    submission text,
    points_awarded boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: applicant_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.applicant_profiles (
    user_id uuid NOT NULL,
    university character varying(255),
    highest_degree character varying(100),
    highest_degree_other character varying(255),
    city_of_residence character varying(100),
    deliver_cities text[],
    background_areas text[],
    background_other character varying(255),
    has_own_transportation boolean DEFAULT false NOT NULL,
    country character varying(100) DEFAULT 'United Arab Emirates'::character varying NOT NULL
);


--
-- Name: application_reviews; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_reviews (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    status public.application_status DEFAULT 'in_progress'::public.application_status NOT NULL,
    admin_id uuid,
    feedback text,
    reviewed_at timestamp with time zone,
    submitted_at timestamp with time zone
);


--
-- Name: applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.applications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    role character varying(50) NOT NULL,
    status character varying(20) DEFAULT 'pending'::character varying NOT NULL,
    full_name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    phone character varying(50),
    country character varying(100),
    password_hash text NOT NULL,
    invite_code character varying(50),
    invited_by_id uuid,
    cv_url text,
    answers jsonb DEFAULT '{}'::jsonb NOT NULL,
    admin_notes text,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    cv_path text
);


--
-- Name: apply_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.apply_questions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    audience character varying(50) NOT NULL,
    question_text text NOT NULL,
    question_type character varying(20) DEFAULT 'text'::character varying NOT NULL,
    required boolean DEFAULT true NOT NULL,
    options jsonb DEFAULT '[]'::jsonb NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: assessment_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.assessment_submissions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    file_url text,
    google_drive_link text,
    comments text,
    submitted_at timestamp with time zone DEFAULT now(),
    bucket character varying(100),
    file_path text
);


--
-- Name: badge_definitions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.badge_definitions (
    id uuid NOT NULL,
    code character varying(50) NOT NULL,
    label character varying(100) NOT NULL,
    description character varying(255),
    icon character varying(50),
    criteria_type character varying(50) NOT NULL,
    threshold integer DEFAULT 1 NOT NULL,
    sort_order integer DEFAULT 0 NOT NULL,
    audience character varying(20) DEFAULT 'ambassador'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: card_seq_person; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.card_seq_person
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: certificates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.certificates (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    type public.certificate_type NOT NULL,
    file_url text NOT NULL,
    generated_at timestamp with time zone DEFAULT now(),
    generated_by uuid,
    payment_session_id uuid,
    workshop_name character varying(255),
    workshop_date character varying(50),
    location character varying(255),
    bucket character varying(100),
    file_path text
);


--
-- Name: checklist_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.checklist_items (
    id uuid NOT NULL,
    module_id uuid NOT NULL,
    section_id uuid,
    item_code character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    sort_order integer DEFAULT 1 NOT NULL,
    is_required boolean DEFAULT true NOT NULL
);


--
-- Name: checklist_modules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.checklist_modules (
    id uuid NOT NULL,
    title character varying(255) NOT NULL,
    sort_order integer DEFAULT 1 NOT NULL
);


--
-- Name: document_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_requests (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    type character varying(50) NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    notes text,
    admin_notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    bucket character varying(100),
    file_path text,
    requested_role character varying(50),
    file_url text
);


--
-- Name: document_templates; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.document_templates (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    key character varying(50) NOT NULL,
    name character varying(255) NOT NULL,
    roles text[] DEFAULT '{}'::text[] NOT NULL,
    body_text text,
    template_file_url character varying(512),
    template_file_path character varying(512),
    type character varying(20) DEFAULT 'letter'::character varying NOT NULL,
    is_system boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id uuid NOT NULL,
    template_id uuid,
    label character varying(255) NOT NULL,
    file_url text NOT NULL,
    generated_by uuid,
    data jsonb DEFAULT '{}'::jsonb NOT NULL,
    generated_at timestamp with time zone DEFAULT now(),
    bucket character varying(100),
    file_path text
);


--
-- Name: epics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.epics (
    id uuid NOT NULL,
    project_id uuid NOT NULL,
    team_id uuid NOT NULL,
    title character varying NOT NULL,
    description text,
    status public.work_status NOT NULL,
    created_by uuid,
    created_at timestamp with time zone
);


--
-- Name: id_cards; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.id_cards (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    role public.user_role NOT NULL,
    card_id character varying(50),
    generated_at timestamp with time zone DEFAULT now()
);


--
-- Name: instructor_bank_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.instructor_bank_details (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    account_holder_name character varying(255),
    bank_name character varying(255),
    iban character varying(50),
    swift_bic character varying(20),
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: instructor_documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.instructor_documents (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    document_type character varying(100) NOT NULL,
    file_url text NOT NULL,
    uploaded_at timestamp with time zone DEFAULT now(),
    bucket character varying(100),
    file_path text
);


--
-- Name: instructor_profiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.instructor_profiles (
    user_id uuid NOT NULL,
    linkedin_url text,
    photo_url text,
    contract_url text,
    signed_contract_url text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    contract_signature_data text,
    contract_signed_at timestamp with time zone,
    contract_path text,
    signed_contract_path text
);


--
-- Name: intern_letters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.intern_letters (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    type character varying(50) NOT NULL,
    file_url text NOT NULL,
    generated_at timestamp with time zone DEFAULT now()
);


--
-- Name: invitation_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.invitation_codes (
    id uuid NOT NULL,
    code character varying(100) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    expires_at timestamp with time zone,
    max_uses integer DEFAULT 20 NOT NULL,
    used_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: lead_comments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lead_comments (
    id uuid NOT NULL,
    lead_id uuid NOT NULL,
    author_id uuid,
    body text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.leads (
    id uuid NOT NULL,
    ambassador_id uuid NOT NULL,
    contact_name character varying(255) NOT NULL,
    company character varying(255),
    type character varying(50) NOT NULL,
    status character varying(50) DEFAULT 'submitted'::character varying NOT NULL,
    notes text,
    points_awarded boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: library_modules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.library_modules (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: library_resources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.library_resources (
    id uuid NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    format character varying(20) NOT NULL,
    file_url text NOT NULL,
    uploader_id uuid,
    module_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    resource_type character varying(10) DEFAULT 'file'::character varying NOT NULL
);


--
-- Name: materials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.materials (
    id uuid NOT NULL,
    created_by uuid,
    title character varying(255) NOT NULL,
    description text,
    link text NOT NULL,
    category character varying(100),
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: mind_map_layouts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mind_map_layouts (
    id uuid NOT NULL,
    epic_id uuid NOT NULL,
    layout jsonb NOT NULL,
    updated_at timestamp with time zone
);


--
-- Name: module_sections; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.module_sections (
    id uuid NOT NULL,
    module_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    sort_order integer DEFAULT 1 NOT NULL
);


--
-- Name: module_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.module_submissions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    module_id uuid NOT NULL,
    file_url text NOT NULL,
    original_filename character varying(255),
    notes_text text,
    status public.module_submission_status DEFAULT 'submitted'::public.module_submission_status NOT NULL,
    feedback text,
    submitted_at timestamp with time zone DEFAULT now(),
    reviewed_at timestamp with time zone,
    reviewer_admin_id uuid,
    bucket character varying(100),
    file_path text
);


--
-- Name: modules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.modules (
    id uuid NOT NULL,
    epic_id uuid NOT NULL,
    title character varying NOT NULL,
    description text,
    created_by uuid,
    created_at timestamp with time zone
);


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notifications (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    body text,
    type character varying(50),
    is_read boolean NOT NULL,
    created_at timestamp with time zone
);


--
-- Name: payment_addons; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_addons (
    id uuid NOT NULL,
    payment_letter_id uuid NOT NULL,
    description character varying(255) NOT NULL,
    amount_aed double precision DEFAULT 0 NOT NULL,
    notes character varying(255),
    sort_order integer DEFAULT 1 NOT NULL
);


--
-- Name: payment_batches; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_batches (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    created_by_admin_id uuid,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: payment_letters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_letters (
    id uuid NOT NULL,
    batch_id uuid,
    instructor_user_id uuid NOT NULL,
    letter_date character varying(50),
    reference character varying(255) DEFAULT 'Facilitator Agreement'::character varying NOT NULL,
    status public.payment_letter_status DEFAULT 'draft'::public.payment_letter_status NOT NULL,
    is_published boolean DEFAULT false NOT NULL,
    pdf_url text,
    signed_pdf_url text,
    instructor_signature_data text,
    signed_at timestamp with time zone,
    admin_notes text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    pdf_path text,
    signed_pdf_path text
);


--
-- Name: payment_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.payment_sessions (
    id uuid NOT NULL,
    payment_letter_id uuid NOT NULL,
    session_date character varying(50),
    workshop_description character varying(255) NOT NULL,
    role public.payment_session_role NOT NULL,
    location character varying(255),
    duration_hours double precision,
    compensation_aed double precision DEFAULT 0 NOT NULL,
    sort_order integer DEFAULT 1 NOT NULL
);


--
-- Name: points_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.points_transactions (
    id uuid NOT NULL,
    ambassador_id uuid NOT NULL,
    amount integer NOT NULL,
    type character varying(50) DEFAULT 'earn'::character varying NOT NULL,
    reason text NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: portal_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.portal_settings (
    id uuid NOT NULL,
    key character varying(100) NOT NULL,
    value text,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: presentation_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.presentation_submissions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    video_link text NOT NULL,
    submitted_at timestamp with time zone DEFAULT now()
);


--
-- Name: project_teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.project_teams (
    project_id uuid NOT NULL,
    team_id uuid NOT NULL
);


--
-- Name: projects; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.projects (
    id uuid NOT NULL,
    title character varying NOT NULL,
    description text,
    status character varying DEFAULT 'active'::character varying NOT NULL,
    created_by uuid NOT NULL,
    created_at timestamp with time zone
);


--
-- Name: proposals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proposals (
    id uuid NOT NULL,
    epic_id uuid NOT NULL,
    proposed_by uuid NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    status character varying NOT NULL,
    reviewed_by uuid,
    reviewed_at timestamp with time zone,
    created_at timestamp with time zone
);


--
-- Name: recommendation_letters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recommendation_letters (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    generated_by uuid NOT NULL,
    signatory_name character varying(255) NOT NULL,
    signatory_title character varying(255) NOT NULL,
    file_url text NOT NULL,
    generated_at timestamp with time zone DEFAULT now()
);


--
-- Name: system_settings; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.system_settings (
    key character varying(255) NOT NULL,
    value character varying(255) NOT NULL
);


--
-- Name: task_assignees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_assignees (
    task_id uuid NOT NULL,
    user_id uuid NOT NULL
);


--
-- Name: task_mind_map_notes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_mind_map_notes (
    task_id uuid NOT NULL,
    note text,
    updated_by uuid,
    updated_at timestamp with time zone
);


--
-- Name: task_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task_submissions (
    id uuid NOT NULL,
    task_id uuid NOT NULL,
    submitted_by uuid NOT NULL,
    link character varying NOT NULL,
    note text,
    status public.submission_status NOT NULL,
    score integer,
    review_comment text,
    submitted_at timestamp with time zone,
    reviewed_at timestamp with time zone
);


--
-- Name: tasks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tasks (
    id uuid NOT NULL,
    module_id uuid NOT NULL,
    title character varying NOT NULL,
    description text,
    status public.work_status NOT NULL,
    due_date timestamp with time zone,
    expected_time numeric(6,2),
    actual_time numeric(6,2),
    created_by uuid,
    created_at timestamp with time zone
);


--
-- Name: teacher_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teacher_sessions (
    id uuid NOT NULL,
    teacher_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    date timestamp with time zone NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying NOT NULL,
    status_note text,
    material_sent boolean DEFAULT false NOT NULL,
    material_link text,
    planned_students integer DEFAULT 0 NOT NULL,
    attended_students integer DEFAULT 0 NOT NULL,
    points_awarded boolean DEFAULT false NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: team_members; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.team_members (
    team_id uuid NOT NULL,
    user_id uuid NOT NULL
);


--
-- Name: teams; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.teams (
    id uuid NOT NULL,
    name character varying NOT NULL,
    leader_id uuid NOT NULL,
    created_at timestamp with time zone
);


--
-- Name: titles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.titles (
    id uuid NOT NULL,
    name character varying(100) NOT NULL,
    min_points integer DEFAULT 0 NOT NULL,
    icon character varying(50),
    color character varying(20),
    sort_order integer DEFAULT 0 NOT NULL,
    audience character varying(20) DEFAULT 'ambassador'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: training_modules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.training_modules (
    id uuid NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    sort_order integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: training_videos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.training_videos (
    id uuid NOT NULL,
    module_id uuid NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    notes text,
    video_path text NOT NULL,
    sort_order integer DEFAULT 1 NOT NULL,
    created_at timestamp with time zone DEFAULT now()
);


--
-- Name: user_checklist_progress; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_checklist_progress (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    checklist_item_id uuid NOT NULL,
    is_completed boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now()
);


--
-- Name: user_training_progress; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.user_training_progress (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    video_id uuid NOT NULL,
    is_completed boolean DEFAULT false NOT NULL,
    completed_at timestamp with time zone
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    full_name character varying(255) NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    roles public.user_role[] DEFAULT '{}'::public.user_role[] NOT NULL,
    status character varying(50) DEFAULT 'active'::character varying NOT NULL,
    invite_code character varying(100),
    invited_by_id uuid,
    must_change_password boolean DEFAULT false NOT NULL,
    phone character varying(50),
    country character varying(100),
    created_at timestamp with time zone DEFAULT now(),
    last_login_at timestamp with time zone,
    recruit_points_awarded boolean DEFAULT false NOT NULL,
    card_number integer,
    photo_path text,
    invitation_code_used character varying(100),
    photo_url text,
    linkedin_url text
);


--
-- Name: video_submissions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.video_submissions (
    id uuid NOT NULL,
    user_id uuid NOT NULL,
    video_no integer NOT NULL,
    youtube_url text,
    summary_text text,
    word_count integer DEFAULT 0 NOT NULL,
    status public.instructor_video_status DEFAULT 'draft'::public.instructor_video_status NOT NULL,
    submitted_at timestamp with time zone
);


--
-- Name: achievements achievements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.achievements
    ADD CONSTRAINT achievements_pkey PRIMARY KEY (id);


--
-- Name: ambassador_tasks ambassador_tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ambassador_tasks
    ADD CONSTRAINT ambassador_tasks_pkey PRIMARY KEY (id);


--
-- Name: applicant_profiles applicant_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applicant_profiles
    ADD CONSTRAINT applicant_profiles_pkey PRIMARY KEY (user_id);


--
-- Name: application_reviews application_reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_reviews
    ADD CONSTRAINT application_reviews_pkey PRIMARY KEY (id);


--
-- Name: application_reviews application_reviews_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_reviews
    ADD CONSTRAINT application_reviews_user_id_key UNIQUE (user_id);


--
-- Name: applications applications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_pkey PRIMARY KEY (id);


--
-- Name: apply_questions apply_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.apply_questions
    ADD CONSTRAINT apply_questions_pkey PRIMARY KEY (id);


--
-- Name: assessment_submissions assessment_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_submissions
    ADD CONSTRAINT assessment_submissions_pkey PRIMARY KEY (id);


--
-- Name: assessment_submissions assessment_submissions_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_submissions
    ADD CONSTRAINT assessment_submissions_user_id_key UNIQUE (user_id);


--
-- Name: badge_definitions badge_definitions_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.badge_definitions
    ADD CONSTRAINT badge_definitions_code_key UNIQUE (code);


--
-- Name: badge_definitions badge_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.badge_definitions
    ADD CONSTRAINT badge_definitions_pkey PRIMARY KEY (id);


--
-- Name: certificates certificates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_pkey PRIMARY KEY (id);


--
-- Name: checklist_items checklist_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_items
    ADD CONSTRAINT checklist_items_pkey PRIMARY KEY (id);


--
-- Name: checklist_modules checklist_modules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_modules
    ADD CONSTRAINT checklist_modules_pkey PRIMARY KEY (id);


--
-- Name: document_requests document_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_requests
    ADD CONSTRAINT document_requests_pkey PRIMARY KEY (id);


--
-- Name: document_templates document_templates_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_templates
    ADD CONSTRAINT document_templates_key_key UNIQUE (key);


--
-- Name: document_templates document_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_templates
    ADD CONSTRAINT document_templates_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: epics epics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.epics
    ADD CONSTRAINT epics_pkey PRIMARY KEY (id);


--
-- Name: id_cards id_cards_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.id_cards
    ADD CONSTRAINT id_cards_pkey PRIMARY KEY (id);


--
-- Name: instructor_bank_details instructor_bank_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instructor_bank_details
    ADD CONSTRAINT instructor_bank_details_pkey PRIMARY KEY (id);


--
-- Name: instructor_bank_details instructor_bank_details_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instructor_bank_details
    ADD CONSTRAINT instructor_bank_details_user_id_key UNIQUE (user_id);


--
-- Name: instructor_documents instructor_documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instructor_documents
    ADD CONSTRAINT instructor_documents_pkey PRIMARY KEY (id);


--
-- Name: instructor_profiles instructor_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instructor_profiles
    ADD CONSTRAINT instructor_profiles_pkey PRIMARY KEY (user_id);


--
-- Name: intern_letters intern_letters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.intern_letters
    ADD CONSTRAINT intern_letters_pkey PRIMARY KEY (id);


--
-- Name: invitation_codes invitation_codes_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitation_codes
    ADD CONSTRAINT invitation_codes_code_key UNIQUE (code);


--
-- Name: invitation_codes invitation_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.invitation_codes
    ADD CONSTRAINT invitation_codes_pkey PRIMARY KEY (id);


--
-- Name: lead_comments lead_comments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_comments
    ADD CONSTRAINT lead_comments_pkey PRIMARY KEY (id);


--
-- Name: leads leads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_pkey PRIMARY KEY (id);


--
-- Name: library_modules library_modules_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.library_modules
    ADD CONSTRAINT library_modules_name_key UNIQUE (name);


--
-- Name: library_modules library_modules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.library_modules
    ADD CONSTRAINT library_modules_pkey PRIMARY KEY (id);


--
-- Name: library_resources library_resources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.library_resources
    ADD CONSTRAINT library_resources_pkey PRIMARY KEY (id);


--
-- Name: materials materials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_pkey PRIMARY KEY (id);


--
-- Name: mind_map_layouts mind_map_layouts_epic_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mind_map_layouts
    ADD CONSTRAINT mind_map_layouts_epic_id_key UNIQUE (epic_id);


--
-- Name: mind_map_layouts mind_map_layouts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mind_map_layouts
    ADD CONSTRAINT mind_map_layouts_pkey PRIMARY KEY (id);


--
-- Name: module_sections module_sections_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.module_sections
    ADD CONSTRAINT module_sections_pkey PRIMARY KEY (id);


--
-- Name: module_submissions module_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.module_submissions
    ADD CONSTRAINT module_submissions_pkey PRIMARY KEY (id);


--
-- Name: modules modules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_pkey PRIMARY KEY (id);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: payment_addons payment_addons_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_addons
    ADD CONSTRAINT payment_addons_pkey PRIMARY KEY (id);


--
-- Name: payment_batches payment_batches_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_batches
    ADD CONSTRAINT payment_batches_pkey PRIMARY KEY (id);


--
-- Name: payment_letters payment_letters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_letters
    ADD CONSTRAINT payment_letters_pkey PRIMARY KEY (id);


--
-- Name: payment_sessions payment_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_sessions
    ADD CONSTRAINT payment_sessions_pkey PRIMARY KEY (id);


--
-- Name: points_transactions points_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.points_transactions
    ADD CONSTRAINT points_transactions_pkey PRIMARY KEY (id);


--
-- Name: portal_settings portal_settings_key_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portal_settings
    ADD CONSTRAINT portal_settings_key_key UNIQUE (key);


--
-- Name: portal_settings portal_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.portal_settings
    ADD CONSTRAINT portal_settings_pkey PRIMARY KEY (id);


--
-- Name: presentation_submissions presentation_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presentation_submissions
    ADD CONSTRAINT presentation_submissions_pkey PRIMARY KEY (id);


--
-- Name: presentation_submissions presentation_submissions_user_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presentation_submissions
    ADD CONSTRAINT presentation_submissions_user_id_key UNIQUE (user_id);


--
-- Name: project_teams project_teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_teams
    ADD CONSTRAINT project_teams_pkey PRIMARY KEY (project_id, team_id);


--
-- Name: projects projects_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_pkey PRIMARY KEY (id);


--
-- Name: proposals proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_pkey PRIMARY KEY (id);


--
-- Name: recommendation_letters recommendation_letters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_letters
    ADD CONSTRAINT recommendation_letters_pkey PRIMARY KEY (id);


--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (key);


--
-- Name: task_assignees task_assignees_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_assignees
    ADD CONSTRAINT task_assignees_pkey PRIMARY KEY (task_id, user_id);


--
-- Name: task_mind_map_notes task_mind_map_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_mind_map_notes
    ADD CONSTRAINT task_mind_map_notes_pkey PRIMARY KEY (task_id);


--
-- Name: task_submissions task_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_submissions
    ADD CONSTRAINT task_submissions_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: teacher_sessions teacher_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_sessions
    ADD CONSTRAINT teacher_sessions_pkey PRIMARY KEY (id);


--
-- Name: team_members team_members_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_pkey PRIMARY KEY (team_id, user_id);


--
-- Name: teams teams_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_pkey PRIMARY KEY (id);


--
-- Name: titles titles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.titles
    ADD CONSTRAINT titles_pkey PRIMARY KEY (id);


--
-- Name: training_modules training_modules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.training_modules
    ADD CONSTRAINT training_modules_pkey PRIMARY KEY (id);


--
-- Name: training_modules training_modules_title_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.training_modules
    ADD CONSTRAINT training_modules_title_key UNIQUE (title);


--
-- Name: training_videos training_videos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.training_videos
    ADD CONSTRAINT training_videos_pkey PRIMARY KEY (id);


--
-- Name: achievements uq_achievement_per_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.achievements
    ADD CONSTRAINT uq_achievement_per_user UNIQUE (ambassador_id, code);


--
-- Name: user_checklist_progress user_checklist_progress_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_checklist_progress
    ADD CONSTRAINT user_checklist_progress_pkey PRIMARY KEY (id);


--
-- Name: user_training_progress user_training_progress_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_training_progress
    ADD CONSTRAINT user_training_progress_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: video_submissions video_submissions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.video_submissions
    ADD CONSTRAINT video_submissions_pkey PRIMARY KEY (id);


--
-- Name: idx_ambassador_tasks_assigned; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_ambassador_tasks_assigned ON public.ambassador_tasks USING btree (assigned_to);


--
-- Name: idx_applications_role_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_applications_role_status ON public.applications USING btree (role, status);


--
-- Name: idx_apply_questions_audience; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_apply_questions_audience ON public.apply_questions USING btree (audience) WHERE is_active;


--
-- Name: idx_assessment_submissions_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_assessment_submissions_user ON public.assessment_submissions USING btree (user_id);


--
-- Name: idx_certificates_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_certificates_user ON public.certificates USING btree (user_id);


--
-- Name: idx_document_requests_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_document_requests_user_id ON public.document_requests USING btree (user_id);


--
-- Name: idx_documents_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_documents_user ON public.documents USING btree (user_id);


--
-- Name: idx_id_cards_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_id_cards_user ON public.id_cards USING btree (user_id);


--
-- Name: idx_instructor_documents_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_instructor_documents_user ON public.instructor_documents USING btree (user_id);


--
-- Name: idx_intern_letters_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_intern_letters_user_id ON public.intern_letters USING btree (user_id);


--
-- Name: idx_invitation_codes_code; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_invitation_codes_code ON public.invitation_codes USING btree (code);


--
-- Name: idx_lead_comments_lead; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_lead_comments_lead ON public.lead_comments USING btree (lead_id);


--
-- Name: idx_leads_ambassador; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_leads_ambassador ON public.leads USING btree (ambassador_id);


--
-- Name: idx_module_submissions_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_module_submissions_user ON public.module_submissions USING btree (user_id);


--
-- Name: idx_payment_addons_letter; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payment_addons_letter ON public.payment_addons USING btree (payment_letter_id);


--
-- Name: idx_payment_letters_instructor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payment_letters_instructor ON public.payment_letters USING btree (instructor_user_id);


--
-- Name: idx_payment_sessions_letter; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_payment_sessions_letter ON public.payment_sessions USING btree (payment_letter_id);


--
-- Name: idx_points_ambassador; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_points_ambassador ON public.points_transactions USING btree (ambassador_id);


--
-- Name: idx_recommendation_letters_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_recommendation_letters_user_id ON public.recommendation_letters USING btree (user_id);


--
-- Name: idx_sessions_teacher; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_sessions_teacher ON public.teacher_sessions USING btree (teacher_id);


--
-- Name: idx_user_checklist_progress_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_checklist_progress_user ON public.user_checklist_progress USING btree (user_id);


--
-- Name: idx_user_training_progress_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_training_progress_user ON public.user_training_progress USING btree (user_id);


--
-- Name: idx_user_training_progress_video; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_user_training_progress_video ON public.user_training_progress USING btree (video_id);


--
-- Name: idx_users_card_number; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX idx_users_card_number ON public.users USING btree (card_number) WHERE (card_number IS NOT NULL);


--
-- Name: idx_video_submissions_user; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_video_submissions_user ON public.video_submissions USING btree (user_id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: uq_users_invite_code; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_users_invite_code ON public.users USING btree (invite_code);


--
-- Name: achievements achievements_ambassador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.achievements
    ADD CONSTRAINT achievements_ambassador_id_fkey FOREIGN KEY (ambassador_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: ambassador_tasks ambassador_tasks_assigned_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ambassador_tasks
    ADD CONSTRAINT ambassador_tasks_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: ambassador_tasks ambassador_tasks_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ambassador_tasks
    ADD CONSTRAINT ambassador_tasks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: applicant_profiles applicant_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applicant_profiles
    ADD CONSTRAINT applicant_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: application_reviews application_reviews_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_reviews
    ADD CONSTRAINT application_reviews_admin_id_fkey FOREIGN KEY (admin_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: application_reviews application_reviews_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_reviews
    ADD CONSTRAINT application_reviews_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: applications applications_invited_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_invited_by_id_fkey FOREIGN KEY (invited_by_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: applications applications_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.applications
    ADD CONSTRAINT applications_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: assessment_submissions assessment_submissions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.assessment_submissions
    ADD CONSTRAINT assessment_submissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: certificates certificates_generated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_generated_by_fkey FOREIGN KEY (generated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: certificates certificates_payment_session_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_payment_session_id_fkey FOREIGN KEY (payment_session_id) REFERENCES public.payment_sessions(id) ON DELETE SET NULL;


--
-- Name: certificates certificates_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.certificates
    ADD CONSTRAINT certificates_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: checklist_items checklist_items_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_items
    ADD CONSTRAINT checklist_items_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.checklist_modules(id) ON DELETE CASCADE;


--
-- Name: checklist_items checklist_items_section_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.checklist_items
    ADD CONSTRAINT checklist_items_section_id_fkey FOREIGN KEY (section_id) REFERENCES public.module_sections(id) ON DELETE CASCADE;


--
-- Name: document_requests document_requests_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.document_requests
    ADD CONSTRAINT document_requests_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: documents documents_generated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_generated_by_fkey FOREIGN KEY (generated_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: documents documents_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.document_templates(id) ON DELETE SET NULL;


--
-- Name: documents documents_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: epics epics_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.epics
    ADD CONSTRAINT epics_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: epics epics_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.epics
    ADD CONSTRAINT epics_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: epics epics_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.epics
    ADD CONSTRAINT epics_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id);


--
-- Name: id_cards id_cards_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.id_cards
    ADD CONSTRAINT id_cards_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: instructor_bank_details instructor_bank_details_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instructor_bank_details
    ADD CONSTRAINT instructor_bank_details_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: instructor_documents instructor_documents_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instructor_documents
    ADD CONSTRAINT instructor_documents_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: instructor_profiles instructor_profiles_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.instructor_profiles
    ADD CONSTRAINT instructor_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: intern_letters intern_letters_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.intern_letters
    ADD CONSTRAINT intern_letters_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: lead_comments lead_comments_author_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_comments
    ADD CONSTRAINT lead_comments_author_id_fkey FOREIGN KEY (author_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: lead_comments lead_comments_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_comments
    ADD CONSTRAINT lead_comments_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.leads(id) ON DELETE CASCADE;


--
-- Name: leads leads_ambassador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.leads
    ADD CONSTRAINT leads_ambassador_id_fkey FOREIGN KEY (ambassador_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: library_resources library_resources_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.library_resources
    ADD CONSTRAINT library_resources_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.library_modules(id) ON DELETE CASCADE;


--
-- Name: library_resources library_resources_uploader_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.library_resources
    ADD CONSTRAINT library_resources_uploader_id_fkey FOREIGN KEY (uploader_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: materials materials_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.materials
    ADD CONSTRAINT materials_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: mind_map_layouts mind_map_layouts_epic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mind_map_layouts
    ADD CONSTRAINT mind_map_layouts_epic_id_fkey FOREIGN KEY (epic_id) REFERENCES public.epics(id);


--
-- Name: module_sections module_sections_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.module_sections
    ADD CONSTRAINT module_sections_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.checklist_modules(id) ON DELETE CASCADE;


--
-- Name: module_submissions module_submissions_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.module_submissions
    ADD CONSTRAINT module_submissions_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.checklist_modules(id) ON DELETE CASCADE;


--
-- Name: module_submissions module_submissions_reviewer_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.module_submissions
    ADD CONSTRAINT module_submissions_reviewer_admin_id_fkey FOREIGN KEY (reviewer_admin_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: module_submissions module_submissions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.module_submissions
    ADD CONSTRAINT module_submissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: modules modules_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: modules modules_epic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.modules
    ADD CONSTRAINT modules_epic_id_fkey FOREIGN KEY (epic_id) REFERENCES public.epics(id);


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: payment_addons payment_addons_payment_letter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_addons
    ADD CONSTRAINT payment_addons_payment_letter_id_fkey FOREIGN KEY (payment_letter_id) REFERENCES public.payment_letters(id) ON DELETE CASCADE;


--
-- Name: payment_batches payment_batches_created_by_admin_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_batches
    ADD CONSTRAINT payment_batches_created_by_admin_id_fkey FOREIGN KEY (created_by_admin_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: payment_letters payment_letters_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_letters
    ADD CONSTRAINT payment_letters_batch_id_fkey FOREIGN KEY (batch_id) REFERENCES public.payment_batches(id) ON DELETE SET NULL;


--
-- Name: payment_letters payment_letters_instructor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_letters
    ADD CONSTRAINT payment_letters_instructor_user_id_fkey FOREIGN KEY (instructor_user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: payment_sessions payment_sessions_payment_letter_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.payment_sessions
    ADD CONSTRAINT payment_sessions_payment_letter_id_fkey FOREIGN KEY (payment_letter_id) REFERENCES public.payment_letters(id) ON DELETE CASCADE;


--
-- Name: points_transactions points_transactions_ambassador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.points_transactions
    ADD CONSTRAINT points_transactions_ambassador_id_fkey FOREIGN KEY (ambassador_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: presentation_submissions presentation_submissions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.presentation_submissions
    ADD CONSTRAINT presentation_submissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: project_teams project_teams_project_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_teams
    ADD CONSTRAINT project_teams_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.projects(id);


--
-- Name: project_teams project_teams_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.project_teams
    ADD CONSTRAINT project_teams_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id);


--
-- Name: projects projects_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.projects
    ADD CONSTRAINT projects_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: proposals proposals_epic_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_epic_id_fkey FOREIGN KEY (epic_id) REFERENCES public.epics(id);


--
-- Name: proposals proposals_proposed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_proposed_by_fkey FOREIGN KEY (proposed_by) REFERENCES public.users(id);


--
-- Name: proposals proposals_reviewed_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_reviewed_by_fkey FOREIGN KEY (reviewed_by) REFERENCES public.users(id);


--
-- Name: recommendation_letters recommendation_letters_generated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_letters
    ADD CONSTRAINT recommendation_letters_generated_by_fkey FOREIGN KEY (generated_by) REFERENCES public.users(id);


--
-- Name: recommendation_letters recommendation_letters_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recommendation_letters
    ADD CONSTRAINT recommendation_letters_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: task_assignees task_assignees_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_assignees
    ADD CONSTRAINT task_assignees_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: task_assignees task_assignees_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_assignees
    ADD CONSTRAINT task_assignees_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: task_mind_map_notes task_mind_map_notes_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_mind_map_notes
    ADD CONSTRAINT task_mind_map_notes_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: task_mind_map_notes task_mind_map_notes_updated_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_mind_map_notes
    ADD CONSTRAINT task_mind_map_notes_updated_by_fkey FOREIGN KEY (updated_by) REFERENCES public.users(id);


--
-- Name: task_submissions task_submissions_submitted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_submissions
    ADD CONSTRAINT task_submissions_submitted_by_fkey FOREIGN KEY (submitted_by) REFERENCES public.users(id);


--
-- Name: task_submissions task_submissions_task_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task_submissions
    ADD CONSTRAINT task_submissions_task_id_fkey FOREIGN KEY (task_id) REFERENCES public.tasks(id);


--
-- Name: tasks tasks_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: tasks tasks_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.modules(id);


--
-- Name: teacher_sessions teacher_sessions_teacher_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teacher_sessions
    ADD CONSTRAINT teacher_sessions_teacher_id_fkey FOREIGN KEY (teacher_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: team_members team_members_team_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_team_id_fkey FOREIGN KEY (team_id) REFERENCES public.teams(id);


--
-- Name: team_members team_members_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.team_members
    ADD CONSTRAINT team_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: teams teams_leader_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.teams
    ADD CONSTRAINT teams_leader_id_fkey FOREIGN KEY (leader_id) REFERENCES public.users(id);


--
-- Name: training_videos training_videos_module_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.training_videos
    ADD CONSTRAINT training_videos_module_id_fkey FOREIGN KEY (module_id) REFERENCES public.training_modules(id) ON DELETE CASCADE;


--
-- Name: user_checklist_progress user_checklist_progress_checklist_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_checklist_progress
    ADD CONSTRAINT user_checklist_progress_checklist_item_id_fkey FOREIGN KEY (checklist_item_id) REFERENCES public.checklist_items(id) ON DELETE CASCADE;


--
-- Name: user_checklist_progress user_checklist_progress_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_checklist_progress
    ADD CONSTRAINT user_checklist_progress_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_training_progress user_training_progress_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_training_progress
    ADD CONSTRAINT user_training_progress_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: user_training_progress user_training_progress_video_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.user_training_progress
    ADD CONSTRAINT user_training_progress_video_id_fkey FOREIGN KEY (video_id) REFERENCES public.training_videos(id) ON DELETE CASCADE;


--
-- Name: users users_invited_by_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_invited_by_id_fkey FOREIGN KEY (invited_by_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: video_submissions video_submissions_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.video_submissions
    ADD CONSTRAINT video_submissions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--


