/** Delivery roles, openings and add-ons (I5-3, I5-4, §G-addons), mirroring
 *  backend/app/routers/sessions/openings.py. */

import { api } from "@/api/client"

export interface DeliveryRole {
  id: string
  name: string
  /** What an instructor is agreeing to when they pick this role. */
  description: string | null
  /** Seniority, lowest first. "The lead" is the lowest sort_order, never a
   *  name match — so renaming or inserting a role doesn't break who's boss. */
  sort_order: number
  is_active: boolean
}

export interface SessionOpening {
  id: string
  session_id: string
  role_id: string
  role_name: string
  slots: number
  /** Derived from assignments/interest — none of these three are stored. */
  filled: number
  remaining: number
  waitlist: number
  amount_aed: string | number | null
  notes: string | null
  /** Whether this role is currently being solicited (B2). Ops sees closed
   *  ones too; instructors only ever see `true` rows. */
  is_open: boolean
  /** True when this came from the cohort's default template rather than a
   *  SessionOpening row of its own (2026-08-01) — saving for this session
   *  overrides the template from then on. */
  inherited?: boolean
}

export interface CohortOpening {
  id: string
  cohort_id: string
  role_id: string
  role_name: string
  slots: number
  amount_aed: string | number | null
  notes: string | null
}

export type AddonSource = "offer" | "interest" | "invite" | "survey" | "payment"
export type AddonStatus = "proposed" | "agreed" | "declined"

export interface SessionAddon {
  id: string
  session_id: string
  user_id: string | null
  user_name: string | null
  role_id: string | null
  role_name: string | null
  description: string
  amount_aed: string | number
  notes: string | null
  source: AddonSource
  status: AddonStatus
  created_at: string | null
  decided_at: string | null
}

/* ── delivery roles ────────────────────────────────────────────────────── */

export const getDeliveryRolesApi = (includeInactive = false) =>
  api.get<DeliveryRole[]>("/sessions/delivery-roles", {
    params: { include_inactive: includeInactive },
  }).then((r) => r.data)

export const createDeliveryRoleApi = (body: { name: string; description?: string | null; sort_order?: number }) =>
  api.post<DeliveryRole>("/sessions/delivery-roles", body).then((r) => r.data)

/** No delete: a role that has ever been assigned is part of the record.
 *  Deactivate it. Renaming is safe — payment letters snapshot the name. */
export const updateDeliveryRoleApi = ({ id, ...body }: {
  id: string
  name?: string
  description?: string | null
  sort_order?: number
  is_active?: boolean
}) => api.patch<DeliveryRole>(`/sessions/delivery-roles/${id}`, body).then((r) => r.data)

/* ── openings ──────────────────────────────────────────────────────────── */

export const getOpeningsApi = (sessionId: string) =>
  api.get<SessionOpening[]>(`/sessions/${sessionId}/openings`).then((r) => r.data)

/** Whole set, not a diff — same as the kit-template BOM endpoint. */
export const setOpeningsApi = ({ sessionId, openings }: {
  sessionId: string
  openings: { role_id: string; slots: number; amount_aed?: number | null; notes?: string | null }[]
}) => api.put<SessionOpening[]>(`/sessions/${sessionId}/openings`, { openings }).then((r) => r.data)

/* ── cohort-level opening defaults (2026-08-01) ──────────────────────────── */

export const getCohortOpeningsApi = (cohortId: string) =>
  api.get<CohortOpening[]>(`/sessions/cohorts/${cohortId}/openings-defaults`).then((r) => r.data)

export const setCohortOpeningsApi = ({ cohortId, openings }: {
  cohortId: string
  openings: { role_id: string; slots: number; amount_aed?: number | null; notes?: string | null }[]
}) => api.put<CohortOpening[]>(`/sessions/cohorts/${cohortId}/openings-defaults`, { openings }).then((r) => r.data)

/* ── add-ons ───────────────────────────────────────────────────────────── */

export const getAddonsApi = (sessionId: string, mine = false) =>
  api.get<SessionAddon[]>(`/sessions/${sessionId}/addons`, { params: { mine } })
    .then((r) => r.data)

/** Status is decided server-side from `source`: ops offers land `agreed`,
 *  instructor requests land `proposed`. Deliberately not settable here. */
export const createAddonApi = ({ sessionId, ...body }: {
  sessionId: string
  description: string
  amount_aed: number
  source?: AddonSource
  user_id?: string | null
  role_id?: string | null
  notes?: string | null
}) => api.post<SessionAddon>(`/sessions/${sessionId}/addons`, body).then((r) => r.data)

export const decideAddonApi = ({ addonId, status }: {
  addonId: string
  status: "agreed" | "declined"
}) => api.put<SessionAddon>(`/sessions/addons/${addonId}/decision`, { status }).then((r) => r.data)

export const updateAddonApi = ({ addonId, ...body }: {
  addonId: string
  description?: string
  amount_aed?: number
}) => api.patch<SessionAddon>(`/sessions/addons/${addonId}`, body).then((r) => r.data)

export const deleteAddonApi = (addonId: string) =>
  api.delete(`/sessions/addons/${addonId}`).then((r) => r.data)

/* ── materials, responsibilities, payment bridge (I5-5 … I5-8) ──────────── */

export interface Material {
  id: string
  program_id: string | null
  cohort_id: string | null
  session_id: string | null
  title: string
  notes: string | null
  /** Signed link for stored files, raw one for external links. */
  url: string | null
  filename: string | null
  sort_order: number
  created_at: string | null
}

export interface SessionMaterials {
  /** program|cohort|session|none — which level these came from. Lets the UI
   *  say "inherited from the program" rather than leaving ops guessing. */
  level: string
  materials: Material[]
}

export type MaterialOwner =
  | { program_id: string }
  | { cohort_id: string }
  | { session_id: string }

export const getMaterialsApi = (owner: MaterialOwner) =>
  api.get<Material[]>("/sessions/materials", { params: owner }).then((r) => r.data)

export const getSessionMaterialsApi = (sessionId: string) =>
  api.get<SessionMaterials>(`/sessions/${sessionId}/materials`).then((r) => r.data)

export const addMaterialLinkApi = ({ owner, ...body }: {
  owner: MaterialOwner
  title: string
  url: string
  notes?: string | null
}) => api.post<Material>("/sessions/materials/link", body, { params: owner }).then((r) => r.data)

export const addMaterialFileApi = ({ owner, title, file, notes }: {
  owner: MaterialOwner
  title: string
  file: File
  notes?: string | null
}) => {
  const form = new FormData()
  form.append("title", title)
  form.append("file", file)
  if (notes) form.append("notes", notes)
  Object.entries(owner).forEach(([k, v]) => form.append(k, v as string))
  return api.post<Material>("/sessions/materials/file", form).then((r) => r.data)
}

export const deleteMaterialApi = (id: string) =>
  api.delete(`/sessions/materials/${id}`).then((r) => r.data)

export interface Responsibilities {
  text: string
  /** Hash of the text — changes exactly when the words do. */
  version: string
  /** Set when a roleId was passed and it resolved to a real role. */
  role_name?: string | null
}

/** Omit roleId for the general text alone (the admin editor). Pass it to get
 *  the combined block — that role's own description, then the general text
 *  ops maintains — an instructor actually reads and agrees to for the role
 *  they're applying for, rather than a generic agreement that says nothing
 *  about the job. */
export const getResponsibilitiesApi = (roleId?: string | null) =>
  api.get<Responsibilities>("/sessions/responsibilities", {
    params: roleId ? { role_id: roleId } : {},
  }).then((r) => r.data)

export const setResponsibilitiesApi = (text: string) =>
  api.put<Responsibilities>("/sessions/responsibilities", { text }).then((r) => r.data)

/** Ticked on the invite. A stale version is refused server-side. */
export const acceptResponsibilitiesApi = ({ sessionId, version }: {
  sessionId: string
  version: string
}) => api.post(`/sessions/${sessionId}/responsibilities/accept`, { version }).then((r) => r.data)
