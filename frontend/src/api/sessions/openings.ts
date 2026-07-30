/** Delivery roles, openings and add-ons (I5-3, I5-4, §G-addons), mirroring
 *  backend/app/routers/sessions/openings.py. */

import { api } from "@/api/client"

export interface DeliveryRole {
  id: string
  name: string
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

export const createDeliveryRoleApi = (body: { name: string; sort_order?: number }) =>
  api.post<DeliveryRole>("/sessions/delivery-roles", body).then((r) => r.data)

/** No delete: a role that has ever been assigned is part of the record.
 *  Deactivate it. Renaming is safe — payment letters snapshot the name. */
export const updateDeliveryRoleApi = ({ id, ...body }: {
  id: string
  name?: string
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
