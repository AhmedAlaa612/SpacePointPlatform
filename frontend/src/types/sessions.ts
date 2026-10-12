/** Programs/cohorts/registration-desk types (V2 R2-3), mirroring the
 * Pydantic schemas in backend/app/schemas/sessions/{programs,cohorts,
 * registration_desk}.py. Kept separate from types/shared.ts, matching how
 * the backend keeps this domain's schemas in their own module. */

export type ProgramType = "workshop" | "course" | "info_session" | "competition";
export type PricingModel = "paid" | "free";

// "percentage": completion_rule_value is 0-100, compared against a cohort's
// present/total_sessions rate. "session_count": completion_rule_value is a
// whole number of sessions the student must be marked present for.
export type CompletionRuleType = "percentage" | "session_count";

export interface Program {
  id: string;
  code: string;
  name: string;
  program_type: ProgramType;
  pricing_model: PricingModel;
  description?: string | null;
  price?: number | null;
  default_capacity?: number | null;
  active: boolean;
  completion_rule_type: CompletionRuleType;
  completion_rule_value: number;
  // Competition domain (2026-08-24) — read-only, derived from
  // `program_type === "competition"`. Not part of the create/update payload.
  is_competition: boolean;
  poster_template_url?: string | null;
  /** Instructor-assessment default (2026-09) — copied once into a new
   * cohort's own assessment assignment at creation; never read live
   * afterwards. See backend Program.default_assessment_config_id. */
  default_assessment_config_id?: string | null;
  default_certificate_template_id?: string | null;
  keep_course_access_after_completion: boolean;
  created_at: string;
}

export interface ProgramCertificateTemplate {
  id: string;
  program_id: string;
  name: string;
  is_default: boolean;
  background_type: "custom" | "dark" | "light";
  background_file_path?: string | null;
  background_file_url?: string | null;
  name_font_size: number;
  name_y: number;
  name_color: string;
  body_text?: string | null;
  body_font_size: number;
  body_y: number;
  body_color: string;
  body_max_width: number;
  body_alignment: "center" | "left" | "right";
  show_signature: boolean;
  signature_image_path?: string | null;
  signature_image_url?: string | null;
  signature_x?: number | null;
  signature_y: number;
  signature_width: number;
  signature_height: number;
  email_subject?: string | null;
  email_body?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export type ProgramCertificateTemplateCreate = Omit<ProgramCertificateTemplate, "id" | "program_id" | "created_at" | "updated_at">;
export type ProgramCertificateTemplateUpdate = Partial<ProgramCertificateTemplateCreate>;

export interface CertificatePreviewRequest {
  recipient_name?: string;
  program_name?: string;
  cohort_name?: string;
  dates?: string;
  location?: string;
  background_type: "custom" | "dark" | "light";
  background_file_path?: string | null;
  name_font_size: number;
  name_y: number;
  name_color: string;
  body_text?: string | null;
  body_font_size: number;
  body_y: number;
  body_color: string;
  body_max_width: number;
  body_alignment: "center" | "left" | "right";
  show_signature: boolean;
  signature_image_path?: string | null;
  signature_x?: number | null;
  signature_y: number;
  signature_width: number;
  signature_height: number;
}

/** planned|registration_open|running|completed|cancelled — see
 * backend/app/models/sessions/cohort.py's own comment for the authoritative list. */
export type CohortStatus = "planned" | "registration_open" | "running" | "completed" | "cancelled";
export type StaffingStatus = "unstaffed" | "open_call" | "staffed";
export type CohortVisibility = "public" | "private";

export interface Cohort {
  id: string;
  program_id: string;
  name: string;
  starts_on?: string | null;
  ends_on?: string | null;
  location?: string | null;
  /** FK to inventory Location — the cohort's venue (2026-08-01). */
  location_id?: string | null;
  location_name?: string | null;
  location_maps_url?: string | null;
  /** Which warehouse equipment for this cohort's sessions comes from. NULL =
   *  resolve it server-side (read effective_warehouse_* below). Separate
   *  from location_id — a location can hold more than one warehouse. */
  warehouse_id?: string | null;
  effective_warehouse_id?: string | null;
  effective_warehouse_name?: string | null;
  capacity?: number | null;
  /** How long each session runs, in hours. Every session in the cohort
   *  inherits this unless it has its own override (see Session.duration_hours). */
  duration_hours?: number | null;
  /** Operational counters, populated only by the LIST endpoint (the cohorts
   *  worklist). Undefined on cohort detail — don't render them as 0 there. */
  sessions_count?: number | null;
  registrations_count?: number | null;
  unstaffed_count?: number | null;
  next_session_date?: string | null;
  lead_instructor_user_id?: string | null;
  status: CohortStatus;
  madar_invitation_batch?: string | null;
  notes?: string | null;
  organization_id?: string | null;
  visibility: CohortVisibility;
  created_at: string;
  /** Ops-set once per cohort — the master poster template link a team's
   *  working copy is duplicated from. */
  poster_template_url?: string | null;
  /** Student-facing title override for the LMS checklist. When set, replaces
   *  the default "Program — Cohort" shown to students. Null means use default. */
  checklist_title_override?: string | null;
  keep_course_access_after_completion: boolean;
  // Convenience join, populated only by the list endpoint.
  program_name?: string | null;
  program_code?: string | null;
  // Same convenience-join pattern — whether this cohort's program has the
  // competition domain's judging tools available (2026-08-24).
  program_is_competition?: boolean;
}

export interface SessionInstructor {
  user_id: string;
  full_name: string;
  /** I5-3: the delivery role's name — roles are data now, not an enum. */
  role: string;
}

/** The actual teaching unit inside a cohort — not just a date. A single-day
 * workshop is a cohort with exactly one Session; a multi-week course has
 * several, each with its own title and instructor(s). Registration always
 * prices off the program, never a per-session override (2026-08-30). */
export interface Session {
  id: string;
  cohort_id: string;
  meeting_date: string;
  starts_at?: string | null;
  title?: string | null;
  material_url?: string | null;
  // unstaffed|open_call|staffed — the W4 staffing marketplace pipeline.
  // Session-scoped, not cohort-scoped (a cohort with several sessions can
  // be partly staffed).
  staffing_status: StaffingStatus;
  created_at: string;
  instructors: SessionInstructor[];
  interested_count?: number;
  /** Instructors this open call is restricted to. Empty = open to everyone. */
  target_user_ids: string[];
  /** NULL = inherits the cohort's location. Read effective_location_* below
   *  for what actually applies — that's already resolved server-side. */
  location_id?: string | null;
  effective_location_id?: string | null;
  effective_location_name?: string | null;
  /** Same override pattern, for which warehouse equipment comes from. */
  warehouse_id?: string | null;
  effective_warehouse_id?: string | null;
  effective_warehouse_name?: string | null;
  /** What actually applies right now — the session's own if it has any,
   *  otherwise whatever the cohort (and, for materials, the program) sets. */
  materials_count?: number;
  kits_count?: number;
  started_at?: string | null;
  completed_at?: string | null;
  /** This session's own override, if it has one — NULL inherits the
   *  cohort's (then the program's) duration. */
  duration_hours?: number | null;
}

export interface GenerateSessionsResult {
  created: Session[];
  skipped: number;
}

/** V2 W4 S4-2/S4-3 — staffing marketplace. */
export interface InstructorInterest {
  user_id: string;
  full_name: string;
  email: string;
  note?: string | null;
  role_id?: string | null;
  role_name?: string | null;
  needs_transport?: boolean;
  needs_ops_support?: boolean;
  travelling_from_other_city?: boolean;
  concerns?: string | null;
  created_at: string;
}

/** Full instructor|facilitator roster for the ops select screen — not
 * interest-only (operator requirement 2026-07-24: pick from the full list,
 * multi-select, select all). */
export interface EligibleInstructor {
  user_id: string;
  full_name: string;
  email: string;
  photo_url?: string | null;
  interested: boolean;
  note?: string | null;
  /** B1 — the role they actually applied for, if any. */
  interest_role_id?: string | null;
  interest_role_name?: string | null;
  /** 2026-08-08 — did this instructor mark the session's resolved city as
   * somewhere they're open to work? False if unresolvable. */
  available_in_city: boolean;
  needs_transport?: boolean;
  needs_ops_support?: boolean;
  travelling_from_other_city?: boolean;
  concerns?: string | null;

  /** Instructor assessment & performance ranking (2026-09) — computed only
   *  for instructors who registered interest (`interested: true`); null for
   *  the rest of the full roster. See services/instructor_assessment/ranking.py. */
  quiz_score?: number | null;
  quiz_critical_correct?: number | null;
  quiz_critical_total?: number | null;
  total_sessions_delivered?: number | null;
  total_hours_delivered?: number | null;
  average_rating?: number | null;
  recent_rating?: number | null;
  priority_score?: number | null;
}

export interface SelectInstructorsResult {
  assigned: string[];
  without_interest: string[];
}

/** S4-3 "Available sessions" instructor page — one open-call session. */
export interface AvailableSession {
  session_id: string;
  cohort_id: string;
  cohort_name: string;
  program_name: string;
  /** What the session actually is. Program + cohort alone don't tell an
   *  instructor what they'd be teaching on the day. */
  title?: string | null;
  location?: string | null;
  meeting_date: string;
  starts_at?: string | null;
  interested_count: number;
  my_interest: boolean;
  my_note?: string | null;
  my_needs_transport?: boolean;
  my_needs_ops_support?: boolean;
  my_travelling_from_other_city?: boolean;
  my_concerns?: string | null;

  /** Instructor assessment (2026-09) — the opportunity to route to when
   *  taking the assessment, and whether this instructor still needs to. */
  cohort_call_id?: string | null;
  assessment_required?: boolean;

  /** I5-5 — what an instructor needs to decide. None of this reached them
   *  before: they got a cohort name, a date and a place. */
  program_type?: string | null;
  description?: string | null;
  /** Full resolved location (2026-08-08) — name + address + maps link,
   *  resolved server-side through `Location`/`City`. */
  location_address?: string | null;
  location_map_url?: string | null;
  duration_hours?: number | null;
  openings: {
    role_id: string;
    role_name: string;
    role_description?: string | null;
    slots: number;
    remaining: number;
    amount_aed?: number | null;
    notes?: string | null;
  }[];
  addons: { description: string; amount_aed: number; notes?: string | null }[];
  responsibilities_accepted: boolean;
}

/** S4-3 "My sessions" instructor page — one session this user is assigned to. */
export interface MySession {
  session_id: string;
  cohort_id: string;
  cohort_name: string;
  program_name: string;
  title?: string | null;
  location?: string | null;
  /** Full resolved location (2026-08-08) — name + address + maps link,
   *  resolved server-side through `Location`/`City`. */
  location_address?: string | null;
  location_maps_url?: string | null;
  location_city?: string | null;
  meeting_date: string;
  starts_at?: string | null;
  my_role: string;
  staffing_status: StaffingStatus;
  started_at?: string | null;
  completed_at?: string | null;
  /** This instructor's own day record (2026-08-28) — all null/undefined
   *  means they haven't checked in yet, same as day_status="draft". */
  att_status?: InstructorAttendance | null;
  checked_in_at?: string | null;
  day_status?: "draft" | "submitted" | "changes_required" | "approved" | null;
}

/** V2 W6 S6-1 — one read-only event in the unified calendar. */
export interface CalendarEvent {
  id: string;
  source: "session" | "teacher_session";
  title: string;
  starts_at: string;
  ends_at?: string | null;
  session_id?: string | null;
  cohort_id?: string | null;
  cohort_name?: string | null;
  program_id?: string | null;
  program_name?: string | null;
  program_type?: ProgramType | null;
  location?: string | null;
  /** Full resolved location (2026-08-08) — the calendar chip shows the
   *  address and links out to the map, not a bare name. */
  location_address?: string | null;
  location_maps_url?: string | null;
  staffing_status?: StaffingStatus | null;
  delivery_status?: "scheduled" | "in_progress" | "completed" | null;
  instructors: SessionInstructor[];
  teacher_session_status?: string | null;
  teacher_name?: string | null;
}

export interface CalendarResult {
  from_date: string;
  to_date: string;
  scope: "ops" | "instructor";
  events: CalendarEvent[];
}

/** W5 S5-1 — instructor session delivery: roster + attendance + start/done. */
export type AttendanceStatus = "present" | "absent";

export interface RosterEntry {
  registration_id: string;
  contact_id: string;
  student_name: string;
  student_phone?: string | null;
  student_email?: string | null;
  student_date_of_birth?: string | null;
  student_grade?: string | null;
  student_organization_name?: string | null;
  student_user_id?: string | null;
  att_status?: AttendanceStatus | null;
  att_method?: "manual" | "qr" | null;
  recorded_at?: string | null;
}

/** Another instructor/facilitator on this same session, and whether
 *  they've checked in yet — the Session Portal's "who's here" strip. */
export interface Teammate {
  user_id: string;
  full_name: string;
  role_name: string;
  is_me: boolean;
  att_status?: AttendanceStatus | null;
  checked_in_at?: string | null;
}

export interface SessionDelivery {
  id: string;
  cohort_id: string;
  cohort_name: string;
  program_name: string;
  location?: string | null;
  /** Full resolved location (2026-08-08) — the instructor's "where do I go
   *  today" screen shows the address and a maps link. */
  location_address?: string | null;
  location_maps_url?: string | null;
  meeting_date: string;
  starts_at?: string | null;
  title?: string | null;
  material_url?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  /** Free-text comment box on the session. One editable blob, not a log. */
  notes?: string | null;
  roster: RosterEntry[];
  reports: SessionReport[];
  teammates: Teammate[];
}

export interface AttendanceResult {
  registration_id: string;
  student_name: string;
  att_status: AttendanceStatus;
  method: "manual" | "qr";
  recorded_at: string;
}

/** W5 S5-2 — a file + notes uploaded after delivering a session. */
export interface SessionReport {
  id: string;
  cohort_id: string;
  session_id?: string | null;
  uploaded_by?: string | null;
  uploaded_by_name?: string | null;
  file_url: string;
  filename: string;
  notes?: string | null;
  created_at: string;
}

export interface CompleteCohortResult {
  cohort: Cohort;
  warnings: string[];
}

export type PaymentStatus = "unpaid" | "partial" | "paid" | "waived" | "refunded";
export type RegistrationStatus = "registered" | "attended" | "completed" | "cancelled" | "no_show";

export interface RegistrationAttendance {
  session_id: string;
  meeting_date: string;
  session_title?: string | null;
  att_status: string;
  recorded_at?: string | null;
}

/** One registration row — a Registration joined with its Contact (and
 * guardian, when payer_contact_id is set). */
export interface Registration {
  id: string;
  contact_id: string;
  student_name: string;
  student_phone?: string | null;
  student_email?: string | null;
  student_date_of_birth?: string | null;
  student_grade?: string | null;
  student_gender?: string | null;
  student_organization_name?: string | null;
  payer_contact_id?: string | null;
  guardian_name?: string | null;
  guardian_phone?: string | null;
  payment_status: PaymentStatus;
  price_charged?: number | null;
  status: RegistrationStatus;
  registered_via: string;
  is_repeat: boolean;
  ticket_sent: boolean;
  onboarding_sent: boolean;
  checked_in: boolean;
  /** Whether a certificate exists at all. Student completion certificates are
   *  emailed as a PDF and never stored, so they have no certificate_url —
   *  check this, not the URL, to know whether one was issued. */
  certificate_issued: boolean;
  certificate_url?: string | null;
  attended_sessions_count?: number;
  total_cohort_sessions_count?: number;
  attendance_records?: RegistrationAttendance[];
  created_at: string;
  /** The linked LMS account's own last_login_at — null means either no
   * account exists yet, or one does but nobody's ever logged into it. */
  last_login_at: string | null;
  // 2026-09-27 — Cohort Media Consent tracking
  media_consent_status?: "consented" | "declined" | "pending";
  media_consent_id?: string | null;
  media_consent_parent_name?: string | null;
  media_consent_parent_phone?: string | null;
  media_consent_parent_email?: string | null;
  media_consent_relationship?: string | null;
  media_consent_signed_date?: string | null;
  media_consent_grants?: string[];
  media_consent_notes?: string | null;
}

export interface CohortMediaConsent {
  id: string;
  cohort_id: string;
  registration_id?: string | null;
  matched_contact_id?: string | null;
  matched_student_name?: string | null;
  student_name_raw?: string | null;
  student_email_raw?: string | null;
  school_name_raw?: string | null;
  parent_name: string;
  relationship?: string | null;
  parent_phone?: string | null;
  parent_email?: string | null;
  consent_choice: "consented" | "declined" | string;
  permission_grants: string[];
  declaration_agreed: boolean;
  date_of_signing?: string | null;
  source: string;
  match_status: "matched" | "unmatched" | "manual" | string;
  match_method?: "email" | "phone" | "manual" | null;
  notes?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CohortMediaConsentSummary {
  total_submissions: number;
  matched_count: number;
  unmatched_count: number;
  consented_count: number;
  declined_count: number;
  pending_registrations_count: number;
  total_registrations_count: number;
  items: CohortMediaConsent[];
}

export interface MediaConsentManualOverrideRequest {
  registration_id: string;
  consent_choice: "consented" | "declined" | "pending";
  parent_name?: string | null;
  relationship?: string | null;
  parent_phone?: string | null;
  parent_email?: string | null;
  notes?: string | null;
}

export type ImportRowDisposition = "create" | "link" | "already_registered" | "review" | "error";

export interface ImportRow {
  row_number: number;
  disposition: ImportRowDisposition;
  data: Record<string, unknown>;
  reason?: string | null;
  contact_id?: string | null;
}

export interface ImportBatchListItem {
  id: string;
  source: "b2b_sheet" | "backfill";
  cohort_id: string;
  filename: string;
  status: "dry_run" | "committed" | "failed";
  summary: Record<string, number>;
  created_at: string;
}

export interface ImportBatch extends ImportBatchListItem {
  rows: ImportRow[];
}

export interface DeskRegistrationInput {
  student_name: string;
  email: string;
  phone: string;
  city?: string;
  // Purely informational (2026-07-24) — no age/minor enforcement anywhere.
  // organization_name resolves or creates a school Organization by name.
  date_of_birth?: string;
  grade?: string;
  gender?: string;
  organization_name?: string;
  // Always optional — no age/minor detection or enforcement anywhere in
  // this system. If given, the parent is linked as guardian/payer.
  parent_name?: string;
  parent_phone?: string;
  parent_email?: string;
  // Which sessions this registration covers — omit for "every session in
  // the cohort" (the common single-session case).
  session_ids?: string[];
  send_ticket_email?: boolean;
  send_welcome_email?: boolean;
}

/** Public ticket page payload (/t/:token). Deliberately narrow — no contact
 *  id, phone, email or payment detail, since the endpoint needs no auth. */
export interface PublicTicket {
  student_name: string;
  program_name: string;
  cohort_name: string;
  dates: string;
  location?: string | null;
  /** Full resolved location (2026-08-08) — the ticket page shows the
   *  address and a maps link under the name, same as the emailed ticket. */
  location_address?: string | null;
  location_maps_url?: string | null;
  ticket_token: string;
  status: string;
  checked_in: boolean;
}

/* ── Cohort-level staffing (2026-08-24) ──────────────────────────────────────
 * Ops opens one call across a set of a cohort's sessions; the instructor
 * answers it once, ticking the days they can do and picking a single role for
 * the whole cohort. See backend/app/services/sessions/cohort_staffing.py. */

export interface CohortCallSessionOption {
  session_id: string;
  title?: string | null;
  meeting_date: string;
  starts_at?: string | null;
  /** Whether this instructor has already ticked it — the card comes back
   *  showing their previous answer rather than a blank form. */
  selected: boolean;
  open_role_ids?: string[];
}

export interface AvailableCohortCall {
  cohort_call_id: string;
  cohort_id: string;
  cohort_name: string;
  program_name: string;
  program_type?: string | null;
  description?: string | null;
  label?: string | null;
  starts_on: string;
  ends_on: string;
  session_count: number;
  location?: string | null;
  location_city?: string | null;
  location_address?: string | null;
  location_map_url?: string | null;
  interested_count: number;
  sessions: CohortCallSessionOption[];
  /** Summed across the call's sessions, so "1 of 3 left" is a cohort-scale
   *  statement. `amount_aed` is the per-session rate. */
  openings: {
    role_id: string;
    role_name: string;
    role_description?: string | null;
    slots: number;
    remaining: number;
    amount_aed?: number | null;
    notes?: string | null;
  }[];

  my_interest: boolean;
  my_role_id?: string | null;
  my_note?: string | null;
  my_needs_transport: boolean;
  my_needs_ops_support: boolean;
  my_travelling_from_other_city: boolean;
  my_concerns?: string | null;

  /** Instructor assessment (2026-09) — see AvailableSession's same-named field. */
  assessment_required?: boolean;
}

/** Two lists on purpose: a cohort call is one decision about a run of days,
 *  while a session opened on its own is still a standalone offer. A session
 *  never appears in both. */
export interface AvailableWork {
  cohort_calls: AvailableCohortCall[];
  single_sessions: AvailableSession[];
}

export interface RegisterCohortInterestBody {
  session_ids: string[];
  role_id?: string | null;
  note?: string | null;
  needs_transport?: boolean;
  needs_ops_support?: boolean;
  travelling_from_other_city?: boolean;
  concerns?: string | null;
  responsibilities_version?: string | null;
}

/** One row of the ops applicant table — one instructor, not one session. */
export interface CohortCallApplicant {
  user_id: string;
  full_name: string;
  email: string;
  role_id?: string | null;
  role_name?: string | null;
  session_ids: string[];
  session_count: number;
  note?: string | null;
  needs_transport: boolean;
  needs_ops_support: boolean;
  travelling_from_other_city: boolean;
  concerns?: string | null;
  responsibilities_accepted_at?: string | null;
  /** The cohort's city is one they already said they'd travel to. */
  available_in_city: boolean;
  status: string;
  already_assigned: boolean;
  created_at?: string | null;

  /** Instructor assessment & performance ranking (2026-09) — see
   *  EligibleInstructor's same-named fields above. */
  quiz_score?: number | null;
  quiz_critical_correct?: number | null;
  quiz_critical_total?: number | null;
  total_sessions_delivered?: number | null;
  total_hours_delivered?: number | null;
  average_rating?: number | null;
  recent_rating?: number | null;
  priority_score?: number | null;
}

export interface CohortAssignment {
  id: string;
  cohort_id: string;
  user_id: string;
  full_name: string;
  email: string;
  role_id: string;
  role_name: string;
  rate_basis: "per_session" | "flat";
  rate_aed?: number | null;
  flat_amount_aed?: number | null;
  status: "active" | "withdrawn";
  source: "call" | "direct";
  session_count: number;
  created_at?: string | null;
}

/* ── Instructor daily loop (2026-08-24) ──────────────────────────────────────
 * Operations process doc §4-§12. See backend/app/services/sessions/day.py. */

export type InstructorAttendance = "present" | "absent";
export type DayStatus = "draft" | "submitted" | "changes_required" | "approved";

export interface ChecklistItem {
  id: string;
  program_id?: string | null;
  cohort_id?: string | null;
  session_id?: string | null;
  /** null = general (every role); set = only that role sees this item,
   *  replacing the general list at this level rather than adding to it. */
  role_id?: string | null;
  title: string;
  description?: string | null;
  /** Can't be ticked off without a photo attached. */
  requires_proof: boolean;
  /** A non-required item is a prompt, not a gate. */
  is_required: boolean;
  sort_order: number;
}

export interface ChecklistLine {
  item_id: string;
  title: string;
  description?: string | null;
  requires_proof: boolean;
  is_required: boolean;
  sort_order: number;
  is_done: boolean;
  note?: string | null;
  proof_report_id?: string | null;
  /** Signed URL, minted per request — never stored. */
  proof_url?: string | null;
}

export interface DayDetail {
  day_id: string;
  session_id: string;
  user_id: string;
  att_status?: InstructorAttendance | null;
  absence_reason?: string | null;
  checked_in_at?: string | null;
  status: DayStatus;
  submitted_at?: string | null;
  reviewed_at?: string | null;
  review_comment?: string | null;
  instructor_notes?: string | null;
  checklist: ChecklistLine[];
  can_submit: boolean;
  /** Everything still outstanding, so it can be shown at once rather than one
   *  failed submit at a time. */
  missing: string[];
}

/** One card in the ops Day Reviews queue. */
export interface DayReview {
  day_id: string;
  session_id: string;
  cohort_id: string;
  cohort_name: string;
  program_name: string;
  session_title?: string | null;
  meeting_date: string;
  user_id: string;
  full_name: string;
  att_status?: InstructorAttendance | null;
  absence_reason?: string | null;
  checked_in_at?: string | null;
  status: DayStatus;
  submitted_at?: string | null;
  review_comment?: string | null;
  instructor_notes?: string | null;
  checklist_done: number;
  checklist_total: number;
}

/** One assigned instructor's state on a Running card — checked in or not,
 *  checklist progress, and whether they've submitted. `day_status` is
 *  `null` for someone who hasn't touched anything yet. */
export interface BoardInstructor {
  user_id: string;
  full_name: string;
  checklist_done: number;
  checklist_total: number;
  att_status?: InstructorAttendance | null;
  checked_in_at?: string | null;
  day_status?: DayStatus | null;
}

/** One session on the ops board — Running/Done, not Needs Review (that's
 *  DayReview, above, from the existing queue). */
export interface BoardSession {
  session_id: string;
  cohort_id: string;
  cohort_name: string;
  program_name: string;
  title?: string | null;
  location?: string | null;
  meeting_date: string;
  starts_at?: string | null;
  staffing_status: StaffingStatus;
  started_at?: string | null;
  completed_at?: string | null;
  /** Populated for Running and Done — a session can be marked done while an
   *  instructor's own report is still unfinished. */
  instructors: BoardInstructor[];
}

export interface SessionBoard {
  running: BoardSession[];
  done: BoardSession[];
  /** Total Done sessions that exist, not just this page. */
  done_total: number;
}

/** One live-quiz run's summary for the ops Report tab. */
export interface SessionGameRun {
  run_id: string;
  game_name: string;
  run_no: number;
  status: "lobby" | "live" | "ended";
  participant_count: number;
  top_score: number;
  current_question_position?: number | null;
  total_questions: number;
}
