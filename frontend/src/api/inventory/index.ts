import { api } from "@/api/client"
import type {
  City,
  Item,
  ItemCategory,
  ItemCategoryDef,
  KitDetail,
  KitListItem,
  KitStatus,
  KitTemplate,
  KitTemplateDetail,
  Location,
  Warehouse,
  Movement,
  MovementReason,
  MyHeldItem,
  MyKit,
  StockLevel,
} from "@/types/inventory"

/* ── locations ─────────────────────────────────────────────────────────── */

export const getLocationsApi = (includeInactive = false) =>
  api.get<Location[]>("/inventory/locations", { params: { include_inactive: includeInactive } })
    .then((r) => r.data)

/** A location is in a city — `city_id` is required; the country is derived
 *  from the city server-side and never sent. */
export const createLocationApi = (body: {
  name: string; city_id: string; notes?: string; address?: string | null; maps_url?: string | null
}) => api.post<Location>("/inventory/locations", body).then((r) => r.data)

export const updateLocationApi = ({ id, ...body }: { id: string } & Partial<Location>) =>
  api.patch<Location>(`/inventory/locations/${id}`, body).then((r) => r.data)

/* ── cities ────────────────────────────────────────────────────────────── */

export const getCitiesApi = (includeInactive = false) =>
  api.get<City[]>("/inventory/cities", { params: { include_inactive: includeInactive } })
    .then((r) => r.data)

export const createCityApi = (body: { name: string; country: string }) =>
  api.post<City>("/inventory/cities", body).then((r) => r.data)

export const updateCityApi = ({ id, ...body }: { id: string } & Partial<City>) =>
  api.patch<City>(`/inventory/cities/${id}`, body).then((r) => r.data)

/* ── warehouses ────────────────────────────────────────────────────────── */

export const getWarehousesApi = (location_id?: string, includeInactive = false) =>
  api.get<Warehouse[]>("/inventory/warehouses", { params: { location_id, include_inactive: includeInactive } })
    .then((r) => r.data)

export const createWarehouseApi = (body: {
  location_id: string; name: string; code?: string; address?: string; notes?: string
}) => api.post<Warehouse>("/inventory/warehouses", body).then((r) => r.data)

export const updateWarehouseApi = ({ id, ...body }: { id: string } & Partial<Warehouse>) =>
  api.patch<Warehouse>(`/inventory/warehouses/${id}`, body).then((r) => r.data)

/* ── items ─────────────────────────────────────────────────────────────── */

export const getItemsApi = (category?: string) =>
  api.get<Item[]>("/inventory/items", { params: category ? { category } : {} }).then((r) => r.data)

export const createItemApi = (body: {
  name: string
  category: ItemCategory
  returnable_default: boolean
  description?: string | null
  variant_group?: string | null
  variant_label?: string | null
}) => api.post<Item>("/inventory/items", body).then((r) => r.data)

export const updateItemApi = ({ id, ...body }: { id: string } & Partial<Item>) =>
  api.patch<Item>(`/inventory/items/${id}`, body).then((r) => r.data)

export const deleteItemApi = (id: string) =>
  api.delete(`/inventory/items/${id}`).then((r) => r.data)

export const setItemImageApi = ({ id, file }: { id: string; file: File }) => {
  const form = new FormData()
  form.append("file", file)
  return api.put<Item>(`/inventory/items/${id}/image`, form).then((r) => r.data)
}

export const removeItemImageApi = (id: string) =>
  api.delete<Item>(`/inventory/items/${id}/image`).then((r) => r.data)

/* ── item categories ───────────────────────────────────────────────────── */

export const getItemCategoriesApi = () =>
  api.get<ItemCategoryDef[]>("/inventory/categories").then((r) => r.data)

export const createItemCategoryApi = (name: string) =>
  api.post<ItemCategoryDef>("/inventory/categories", { name }).then((r) => r.data)

export const updateItemCategoryApi = ({ id, ...body }: {
  id: string; name?: string
}) => api.patch<ItemCategoryDef>(`/inventory/categories/${id}`, body).then((r) => r.data)

/** Refused with a 409 while any item still uses this category — reassign
 *  them to another category first. */
export const deleteItemCategoryApi = (id: string) =>
  api.delete(`/inventory/categories/${id}`).then((r) => r.data)

/* ── templates ─────────────────────────────────────────────────────────── */

export const getTemplatesApi = () =>
  api.get<KitTemplate[]>("/inventory/templates").then((r) => r.data)

export const getTemplateApi = (id: string) =>
  api.get<KitTemplateDetail>(`/inventory/templates/${id}`).then((r) => r.data)

export const createTemplateApi = (body: { name: string; code: string }) =>
  api.post<KitTemplate>("/inventory/templates", body).then((r) => r.data)

export const updateTemplateApi = ({ id, ...body }: {
  id: string; name?: string; code?: string; is_active?: boolean
}) => api.patch<KitTemplate>(`/inventory/templates/${id}`, body).then((r) => r.data)

/** Refused with a 409 while any kit was built from this template — retire
 *  those kits first. */
export const deleteTemplateApi = (id: string) =>
  api.delete(`/inventory/templates/${id}`).then((r) => r.data)

/** Replaces the whole bill of materials — the API takes the full list, not a diff. */
export const setTemplateItemsApi = ({ id, lines }: {
  id: string
  lines: { item_id: string; required_qty: number }[]
}) => api.put<KitTemplateDetail>(`/inventory/templates/${id}/items`, lines).then((r) => r.data)

/* ── kits ──────────────────────────────────────────────────────────────── */

export const getKitsApi = (params: {
  location_id?: string
  warehouse_id?: string
  holder_user_id?: string
  template_id?: string
  status?: string
  /** On the shelf (nobody holding it) and in working order. */
  available_only?: boolean
} = {}) => api.get<KitListItem[]>("/inventory/kits", { params }).then((r) => r.data)

export const getKitApi = (id: string) =>
  api.get<KitDetail>(`/inventory/kits/${id}`).then((r) => r.data)

export const createKitApi = (body: {
  template_id: string
  label: string
  current_warehouse_id: string
}) => api.post<KitDetail>("/inventory/kits", body).then((r) => r.data)

export const bulkCreateKitsApi = (body: {
  template_id: string
  warehouse_id: string
  count: number
  complete: boolean
}) => api.post<KitListItem[]>("/inventory/kits/bulk", body).then((r) => r.data)

export const updateKitApi = ({ id, ...body }: {
  id: string
  label?: string
  status?: KitStatus
  notes?: string | null
}) => api.patch<KitDetail>(`/inventory/kits/${id}`, body).then((r) => r.data)

export const moveKitApi = ({ id, ...body }: {
  id: string
  to_warehouse_id?: string
  to_user_id?: string
  reason: MovementReason
  due_back_on?: string | null
  note?: string | null
}) => api.post<Movement>(`/inventory/kits/${id}/move`, body).then((r) => r.data)

export const getKitHistoryApi = (id: string) =>
  api.get<Movement[]>(`/inventory/kits/${id}/movements`).then((r) => r.data)

/** Set a kit's contents straight from a count. `fromShelf` ticked draws the
 *  difference off (or back onto) the kit's own warehouse shelf; unticked
 *  treats it as arriving from nowhere in particular (or a loss/correction
 *  with no destination) — see backend `count_kit()`. */
export const countKitApi = ({ kitId, reason, fromShelf, lines }: {
  kitId: string
  reason: string
  fromShelf: boolean
  lines: { item_id: string; new_qty: number }[]
}) => api.post<Movement[]>(`/inventory/kits/${kitId}/count`, {
  reason, from_shelf: fromShelf, lines,
}).then((r) => r.data)

export interface KitSession {
  session_id: string
  cohort_id: string
  cohort_name: string
  program_name: string
  title: string
  meeting_date: string
  starts_at: string | null
  return_status: "returned" | "return_later" | null
  received: boolean
  ops_confirmed: boolean
}

/** Every session this kit has been earmarked for — past and future. */
export const getKitSessionsApi = (id: string) =>
  api.get<KitSession[]>(`/inventory/kits/${id}/sessions`).then((r) => r.data)

/** People a kit can be handed to. Separate from /admin/users, which is
 *  admin-only — ops needs a recipient picker, not user management. */
export const getHoldersApi = () =>
  api.get<{ id: string; full_name: string; roles: string[] }[]>("/inventory/holders")
    .then((r) => r.data)

/* ── stock and the ledger ──────────────────────────────────────────────── */

/** `warehouse_id` is the real filter; `location_id` is a convenience that
 *  widens it to every warehouse under that location. */
export const getStockApi = (params: { location_id?: string; warehouse_id?: string; item_id?: string } = {}) =>
  api.get<StockLevel[]>("/inventory/stock", { params }).then((r) => r.data)

export const moveStockApi = (body: {
  item_id: string
  qty: number
  reason: MovementReason
  from_warehouse_id?: string
  from_kit_id?: string
  to_warehouse_id?: string
  to_user_id?: string
  to_kit_id?: string
  note?: string | null
}) => api.post<Movement>("/inventory/stock/move", body).then((r) => r.data)

export const adjustStockApi = (body: {
  item_id: string
  warehouse_id: string
  new_qty: number
  reason: string
}) => api.post<Movement>("/inventory/stock/adjust", body).then((r) => r.data)

/** One stocktake, many item/warehouse counts, one reason. Skips lines that
 *  didn't change server-side; only send lines the caller actually edited. */
export const adjustStockBulkApi = (body: {
  reason: string
  levels: { item_id: string; warehouse_id: string; new_qty: number }[]
}) => api.post<Movement[]>("/inventory/stock/adjust-bulk", body).then((r) => r.data)

export const getOverdueApi = () =>
  api.get<Movement[]>("/inventory/overdue").then((r) => r.data)

export const confirmMovementApi = (id: string) =>
  api.post<Movement>(`/inventory/movements/${id}/confirm`).then((r) => r.data)

/* ── the session loop ──────────────────────────────────────────────────── */

export interface SessionKitStatus {
  kits: {
    kit_id: string
    label: string
    template_name: string
    status: string
    location_name: string
    pre_checked: boolean
    post_checked: boolean
    /** No custody leg: these are the instructor's own report and ops's
     *  review of it, not a movement or a holder. */
    received: boolean
    received_at: string | null
    return_status: "returned" | "return_later" | null
    returned_at: string | null
    ops_confirmed: boolean
    /** True when this kit came from the cohort's default assignment rather
     *  than this session's own explicit pick (2026-08-01 cohort kit defaults). */
    inherited?: boolean
  }[]
  outstanding_post_checks: string[]
  /** Mirrors exactly what mark_done enforces, so the UI can disable the
   *  button rather than let someone press it and get a 409. */
  can_finish: boolean
  /** Whether the list above is this session's own assignment, inherited from
   *  the cohort's defaults, or empty. */
  level?: "session" | "cohort" | "none"
}

/* ── cohort-level kit defaults (2026-08-01) ──────────────────────────────
 * What a session in this cohort is equipped with until it picks its own —
 * same "set it once, override per-session" pattern as MaterialsPanel. */

export interface CohortKit {
  kit_id: string
  label: string
  template_name: string
  location_name: string
}

export interface CohortKitStatus {
  kits: CohortKit[]
}

export const getCohortKitsApi = (cohortId: string) =>
  api.get<CohortKitStatus>(`/inventory/cohorts/${cohortId}/kits-defaults`).then((r) => r.data)

export const setCohortKitsApi = ({ cohortId, kitIds }: { cohortId: string; kitIds: string[] }) =>
  api.put<CohortKitStatus>(`/inventory/cohorts/${cohortId}/kits-defaults`, { kit_ids: kitIds }).then((r) => r.data)

export const removeCohortKitApi = ({ cohortId, kitId }: { cohortId: string; kitId: string }) =>
  api.delete<CohortKitStatus>(`/inventory/cohorts/${cohortId}/kits-defaults/${kitId}`).then((r) => r.data)

export interface ExpectedCount {
  item_id: string
  item_name: string
  required: number
  expected: number
}

export const getSessionKitsApi = (sessionId: string) =>
  api.get<SessionKitStatus>(`/inventory/sessions/${sessionId}/kits`).then((r) => r.data)

export const setSessionKitsApi = ({ sessionId, kitIds }: { sessionId: string; kitIds: string[] }) =>
  api.put<SessionKitStatus>(`/inventory/sessions/${sessionId}/kits`, { kit_ids: kitIds })
    .then((r) => r.data)

export const removeSessionKitApi = ({ sessionId, kitId }: { sessionId: string; kitId: string }) =>
  api.delete<SessionKitStatus>(`/inventory/sessions/${sessionId}/kits/${kitId}`).then((r) => r.data)

export const getCheckFormApi = ({ sessionId, kitId }: { sessionId: string; kitId: string }) =>
  api.get<ExpectedCount[]>(`/inventory/sessions/${sessionId}/kits/${kitId}/check`).then((r) => r.data)

export const submitCheckApi = ({ sessionId, kitId, ...body }: {
  sessionId: string
  kitId: string
  phase: "pre" | "post" | "adhoc"
  counts?: Record<string, number>
  skipped?: boolean
  note?: string | null
}) => api.post(`/inventory/sessions/${sessionId}/kits/${kitId}/check`, body).then((r) => r.data)

/** The instructor confirming they have these kits — one, several, or all
 *  selected at once. No custody movement behind this. */
export const receiveSessionKitsApi = ({ sessionId, kitIds }: { sessionId: string; kitIds: string[] }) =>
  api.post<SessionKitStatus>(`/inventory/sessions/${sessionId}/kits/receive`, { kit_ids: kitIds })
    .then((r) => r.data)

/** The instructor reporting kits back, or saying they're coming back later.
 *  No location to pick — ops decides where a kit lands when it reviews this. */
export const markKitsReturnedApi = ({ sessionId, kitIds, later, note }: {
  sessionId: string
  kitIds: string[]
  later?: boolean
  note?: string | null
}) => api.post<SessionKitStatus>(`/inventory/sessions/${sessionId}/kits/mark-returned`, {
  kit_ids: kitIds, later: later ?? false, note: note ?? null,
}).then((r) => r.data)

/** Ops reviewing the instructor's report in the session review screen.
 *  `restockWarehouseId` is optional — a kit that never left has nothing to move. */
export const confirmKitReturnsApi = ({ sessionId, kitIds, restockWarehouseId }: {
  sessionId: string
  kitIds: string[]
  restockWarehouseId?: string | null
}) => api.post<SessionKitStatus>(`/inventory/sessions/${sessionId}/kits/confirm-returns`, {
  kit_ids: kitIds, restock_warehouse_id: restockWarehouseId ?? null,
}).then((r) => r.data)

/* ── storekeeper fulfilment (I3-1) ─────────────────────────────────────── */

export interface FulfilmentShortage {
  item_id: string
  item_name: string
  required: number
  actual: number
  short_by: number
  /** On the shelf in this kit's own warehouse — what makes the queue
   *  actionable rather than merely informative. */
  available: number
}

export interface FulfilmentKit {
  kit_id: string
  label: string
  template_name: string
  status: string
  location_id: string
  location_name: string
  warehouse_id: string
  warehouse_name: string
  out_with_someone: boolean
  /** Set = someone looked and the shelf was empty. Null = nobody has been to
   *  it yet. That difference is the only thing this queue stores. */
  awaiting_parts_since: string | null
  awaiting_parts_note: string | null
  shortages: FulfilmentShortage[]
  fixable_now: number
}

/** `locationId` narrows to every warehouse under that location — a
 *  convenience filter, not the unit of "where." */
export const getFulfilmentQueueApi = (locationId?: string) =>
  api.get<FulfilmentKit[]>("/inventory/fulfilment", {
    params: locationId ? { location_id: locationId } : {},
  }).then((r) => r.data)

/** `fromWarehouseId` omitted means the kit's own shelf. */
export const fulfilKitApi = ({ kitId, lines, fromWarehouseId }: {
  kitId: string
  lines: { item_id: string; qty: number }[]
  fromWarehouseId?: string | null
}) => api.post<Movement[]>(`/inventory/fulfilment/${kitId}/fulfil`, {
  lines, from_warehouse_id: fromWarehouseId ?? null,
}).then((r) => r.data)

export const setAwaitingPartsApi = ({ kitId, awaiting, note }: {
  kitId: string
  awaiting: boolean
  note?: string | null
}) => api.put<FulfilmentKit>(`/inventory/fulfilment/${kitId}/awaiting`, {
  awaiting, note: note ?? null,
}).then((r) => r.data)

/* ── equipment pickup (I2-7) ───────────────────────────────────────────── */

export interface EquipmentSearchResult {
  item_id: string
  item_name: string
  category: string
  available: number
  returnable: boolean
  description: string | null
  image_url: string | null
}

export interface TakenEquipment {
  item_id: string
  item_name: string
  qty_taken: number
  qty_returned: number
  outstanding: number
  returnable: boolean
  /** Persisted "coming back later" — survives a reload. Always false once
   *  actually returned. */
  later: boolean
}

export interface SessionEquipment {
  /** Derived from the assigned kits — ops moves them to the session's
   *  warehouse first, so that is where the instructor collects. Null when
   *  there is nothing to derive from, which is the only time the UI asks. */
  warehouse_id: string | null
  warehouse_name: string | null
  lines: TakenEquipment[]
  outstanding_count: number
}

export const getSessionEquipmentApi = (sessionId: string) =>
  api.get<SessionEquipment>(`/inventory/sessions/${sessionId}/equipment`).then((r) => r.data)

/** B3: the whole shelf at the pickup point by default. `q` is an optional
 *  narrowing filter, not a gate — omitting it still returns everything. */
export const searchEquipmentApi = ({ sessionId, q = "", warehouseId }: {
  sessionId: string
  q?: string
  warehouseId?: string | null
}) => api.get<EquipmentSearchResult[]>(`/inventory/sessions/${sessionId}/equipment/search`, {
  params: { q, ...(warehouseId ? { warehouse_id: warehouseId } : {}) },
}).then((r) => r.data)

export const takeEquipmentApi = ({ sessionId, lines, warehouseId, note }: {
  sessionId: string
  lines: { item_id: string; qty: number }[]
  warehouseId?: string | null
  note?: string | null
}) => api.post<Movement[]>(`/inventory/sessions/${sessionId}/equipment/take`, {
  lines, warehouse_id: warehouseId ?? null, note: note ?? null,
}).then((r) => r.data)

/** Lines left out stay outstanding — that is how "returning later" is
 *  recorded, because it is what actually happened. */
export const returnEquipmentApi = ({ sessionId, lines, toWarehouseId }: {
  sessionId: string
  lines: { item_id: string; qty: number }[]
  toWarehouseId?: string | null
}) => api.post<Movement[]>(`/inventory/sessions/${sessionId}/equipment/return`, {
  lines, to_warehouse_id: toWarehouseId ?? null,
}).then((r) => r.data)

/** Flags items as coming back later — or, if one was already marked
 *  returned, undoes that and flags it instead. Same toggle a kit's return
 *  report gets. */
export const markEquipmentReturnLaterApi = ({ sessionId, itemIds }: {
  sessionId: string
  itemIds: string[]
}) => api.post<void>(`/inventory/sessions/${sessionId}/equipment/return-later`, {
  item_ids: itemIds,
}).then((r) => r.data)

/* ── instructor-facing ─────────────────────────────────────────────────── */

export const getMyKitsApi = () =>
  api.get<MyKit[]>("/inventory/my-kits").then((r) => r.data)

export const getMyMerchApi = () =>
  api.get<{ item_id: string; item_name: string; qty: number; due_back_on: string | null }[]>(
    "/inventory/my-merch",
  ).then((r) => r.data)

/* ── my holdings — self-serve returns (2026-08-01) ───────────────────────── */

export const getMyHeldItemsApi = () =>
  api.get<MyHeldItem[]>("/inventory/my-holdings/items").then((r) => r.data)

export const returnMyKitApi = ({ kitId, toWarehouseId, note }: { kitId: string; toWarehouseId?: string | null; note?: string | null }) =>
  api.post<Movement>(`/inventory/my-holdings/kits/${kitId}/return`, {
    to_warehouse_id: toWarehouseId ?? null,
    note: note ?? null,
  }).then((r) => r.data)

export const returnMyItemApi = ({ itemId, qty, toWarehouseId, note }: {
  itemId: string
  qty: number
  toWarehouseId?: string | null
  note?: string | null
}) => api.post<Movement>(`/inventory/my-holdings/items/${itemId}/return`, {
  qty, to_warehouse_id: toWarehouseId ?? null, note: note ?? null,
}).then((r) => r.data)

/* ── public scan (no auth) ─────────────────────────────────────────────── */

export interface PublicKit {
  label: string
  template_name: string
  status: string
  owner: string
  contact_email: string
}

export const getPublicKitApi = (token: string) =>
  api.get<PublicKit>(`/public/kit/${token}`).then((r) => r.data)
