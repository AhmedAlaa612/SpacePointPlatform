/** Programs/cohorts/registration-desk types (V2 R2-3), mirroring the
 * Pydantic schemas in backend/app/schemas/sessions/{programs,cohorts,
 * registration_desk}.py. Kept separate from types/shared.ts, matching how
 * the backend keeps this domain's schemas in their own module. */

export type ProgramType = "workshop" | "course" | "info_session";
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
  created_at: string;
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
  capacity?: number | null;
  lead_instructor_user_id?: string | null;
  status: CohortStatus;
  madar_invitation_batch?: string | null;
  notes?: string | null;
  organization_id?: string | null;
  visibility: CohortVisibility;
  created_at: string;
  // Convenience join, populated only by the list endpoint.
  program_name?: string | null;
  program_code?: string | null;
}

export interface SessionInstructor {
  user_id: string;
  full_name: string;
  role: "lead" | "co";
}

/** The actual teaching unit inside a cohort — not just a date. A single-day
 * workshop is a cohort with exactly one Session; a multi-week course has
 * several, each with its own title, instructor(s), and (optionally) its own
 * price override. */
export interface Session {
  id: string;
  cohort_id: string;
  meeting_date: string;
  starts_at?: string | null;
  title?: string | null;
  material_url?: string | null;
  price?: number | null;
  // unstaffed|open_call|staffed — the W4 staffing marketplace pipeline.
  // Session-scoped, not cohort-scoped (a cohort with several sessions can
  // be partly staffed).
  staffing_status: StaffingStatus;
  created_at: string;
  instructors: SessionInstructor[];
  interested_count?: number;
  /** Instructors this open call is restricted to. Empty = open to everyone. */
  target_user_ids: string[];
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
}

/** S4-3 "My sessions" instructor page — one session this user is assigned to. */
export interface MySession {
  session_id: string;
  cohort_id: string;
  cohort_name: string;
  program_name: string;
  title?: string | null;
  location?: string | null;
  meeting_date: string;
  starts_at?: string | null;
  my_role: "lead" | "co";
  staffing_status: StaffingStatus;
  started_at?: string | null;
  completed_at?: string | null;
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
  att_status?: AttendanceStatus | null;
  att_method?: "manual" | "qr" | null;
  recorded_at?: string | null;
}

export interface SessionDelivery {
  id: string;
  cohort_id: string;
  cohort_name: string;
  program_name: string;
  location?: string | null;
  meeting_date: string;
  starts_at?: string | null;
  title?: string | null;
  material_url?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  roster: RosterEntry[];
  reports: SessionReport[];
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
}

/** Public ticket page payload (/t/:token). Deliberately narrow — no contact
 *  id, phone, email or payment detail, since the endpoint needs no auth. */
export interface PublicTicket {
  student_name: string;
  program_name: string;
  cohort_name: string;
  dates: string;
  location?: string | null;
  ticket_token: string;
  status: string;
  checked_in: boolean;
}
