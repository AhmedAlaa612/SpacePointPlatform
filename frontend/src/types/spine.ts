/** Spine domain types (V2 R2-4) — contacts admin + merge review. Mirrors
 * backend/app/schemas/spine/contacts.py. Kept separate from shared.ts: these
 * are Contact/Organization roles, a different concept from the platform's
 * User `Role` (admin/intern/.../operations) already defined there. */

/** contact_roles values (see backend/app/models/spine/contact.py) — a
 * contact can hold several at once. */
export type ContactRole =
  | "student"
  | "parent_guardian"
  | "teacher"
  | "school_admin"
  | "sponsor_rep"
  | "gov_official"
  | "alumnus"
  | "instructor"
  | "ambassador"
  | "intern"
  | "other";

export const CONTACT_ROLE_LABEL: Record<ContactRole, string> = {
  student: "Student",
  parent_guardian: "Parent/Guardian",
  teacher: "Teacher",
  school_admin: "School Admin",
  sponsor_rep: "Sponsor Rep",
  gov_official: "Gov Official",
  alumnus: "Alumnus",
  instructor: "Instructor",
  ambassador: "Ambassador",
  intern: "Intern",
  other: "Other",
};

export type LifecycleStage = "subscriber" | "lead" | "mql" | "sql" | "customer" | "alumni";

export const LIFECYCLE_STAGE_LABEL: Record<LifecycleStage, string> = {
  subscriber: "Subscriber",
  lead: "Lead",
  mql: "MQL",
  sql: "SQL",
  customer: "Customer",
  alumni: "Alumni",
};

/** guardian_of|child_of|sibling_of|spouse_of|other — see ContactRelationship. */
export type ContactRelationType = "guardian_of" | "child_of" | "sibling_of" | "spouse_of" | "other";

export const RELATION_LABEL: Record<ContactRelationType, string> = {
  guardian_of: "Guardian of",
  child_of: "Child of",
  sibling_of: "Sibling of",
  spouse_of: "Spouse of",
  other: "Other",
};

export interface ContactBrief {
  id: string;
  full_name: string;
  contact_roles: string[];
  primary_phone_e164?: string | null;
  whatsapp_e164?: string | null;
  email?: string | null;
  lifecycle_stage?: string | null;
}

export interface ContactListItem {
  id: string;
  full_name: string;
  contact_roles: string[];
  primary_phone_e164?: string | null;
  whatsapp_e164?: string | null;
  email?: string | null;
  country?: string | null;
  city?: string | null;
  lifecycle_stage: string;
  organization_id?: string | null;
  created_at: string;
}

export interface ContactSearchResponse {
  items: ContactListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ContactRelationshipOut {
  id: string;
  contact_id: string;
  related_contact_id: string;
  relation: string;
  created_at: string;
  direction: "outgoing" | "incoming";
  other_contact: ContactBrief | null;
}

export interface ContactDetail {
  id: string;
  full_name: string;
  contact_roles: string[];
  primary_phone_e164?: string | null;
  whatsapp_e164?: string | null;
  secondary_phones: string[];
  email?: string | null;
  preferred_language: string;
  country?: string | null;
  city?: string | null;
  date_of_birth?: string | null;
  grade?: string | null;
  lifecycle_stage: string;
  owner_user_id?: string | null;
  organization_id?: string | null;
  organization_name?: string | null;
  merged_into_id?: string | null;
  notes?: string | null;
  created_at: string;
  updated_at?: string | null;
  relationships: ContactRelationshipOut[];
}

/** One row of a contact's role timeline (2026-07-24) — GET
 * /spine/contacts/{id}/role-history. `role` is whatever vocabulary was
 * actually mutated: a raw platform Role (applicant/instructor/...) for a
 * staff account's role edits, or a ContactRole (student/parent_guardian/...)
 * for contact-only changes — see backend/app/services/spine/role_history.py. */
export interface ContactRoleEventOut {
  id: string;
  role: string;
  action: "added" | "removed";
  source: string;
  changed_by_user_id?: string | null;
  changed_by_name?: string | null;
  occurred_at: string;
}

export const ROLE_EVENT_SOURCE_LABEL: Record<string, string> = {
  registration: "Public registration",
  desk: "Registration desk",
  import: "Bulk import",
  contact_edit: "Contact edited",
  user_role_edit: "Role changed by admin",
  user_created: "Account created",
  backfill_initial: "Linked from user account",
};

export type ContactUpdate = Partial<{
  full_name: string;
  contact_roles: string[];
  primary_phone_e164: string | null;
  whatsapp_e164: string | null;
  secondary_phones: string[];
  email: string | null;
  preferred_language: string;
  country: string | null;
  city: string | null;
  date_of_birth: string | null;
  grade: string | null;
  lifecycle_stage: string;
  owner_user_id: string | null;
  organization_id: string | null;
  notes: string | null;
}>;

export interface Organization {
  id: string;
  name_latin: string;
  name_arabic?: string | null;
  org_type: string;
  country?: string | null;
  city?: string | null;
  primary_contact_id?: string | null;
  owner_user_id?: string | null;
  notes?: string | null;
  created_at: string;
}

export type OrganizationCreate = Omit<Organization, "id" | "created_at">;
export type OrganizationUpdate = Partial<OrganizationCreate>;

/** phone_match|import_ambiguous — never a name-based reason; name plays no
 * role in identity matching anywhere in this system. */
export type MergeReviewReason = "phone_match" | "import_ambiguous";
export type MergeReviewStatus = "pending" | "merged" | "kept_separate" | "linked_household";

export interface MergeReviewOut {
  id: string;
  reason: string;
  status: string;
  detail: Record<string, unknown> | null;
  created_at: string;
  resolved_by?: string | null;
  resolved_at?: string | null;
  candidate_a: ContactBrief | null;
  candidate_b: ContactBrief | null;
}

export interface MergeResolveRequest {
  action: "merge" | "keep_separate" | "link_household";
  winner_id?: string | null;
  relation?: string | null;
}
