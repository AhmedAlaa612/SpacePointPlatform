import { api } from "@/api/client"
import type {
  Item,
  ItemCategory,
  KitDetail,
  KitListItem,
  KitStatus,
  KitTemplate,
  KitTemplateDetail,
  Location,
  Movement,
  MovementReason,
  MyKit,
  StockLevel,
} from "@/types/inventory"

/* ── locations ─────────────────────────────────────────────────────────── */

export const getLocationsApi = (includeInactive = false) =>
  api.get<Location[]>("/inventory/locations", { params: { include_inactive: includeInactive } })
    .then((r) => r.data)

export const createLocationApi = (body: { name: string; country: string; notes?: string }) =>
  api.post<Location>("/inventory/locations", body).then((r) => r.data)

export const updateLocationApi = ({ id, ...body }: { id: string } & Partial<Location>) =>
  api.patch<Location>(`/inventory/locations/${id}`, body).then((r) => r.data)

/* ── items ─────────────────────────────────────────────────────────────── */

export const getItemsApi = (category?: string) =>
  api.get<Item[]>("/inventory/items", { params: category ? { category } : {} }).then((r) => r.data)

export const createItemApi = (body: {
  name: string
  category: ItemCategory
  is_consumable: boolean
  returnable_default: boolean
}) => api.post<Item>("/inventory/items", body).then((r) => r.data)

export const updateItemApi = ({ id, ...body }: { id: string } & Partial<Item>) =>
  api.patch<Item>(`/inventory/items/${id}`, body).then((r) => r.data)

export const deleteItemApi = (id: string) =>
  api.delete(`/inventory/items/${id}`).then((r) => r.data)

/* ── templates ─────────────────────────────────────────────────────────── */

export const getTemplatesApi = () =>
  api.get<KitTemplate[]>("/inventory/templates").then((r) => r.data)

export const getTemplateApi = (id: string) =>
  api.get<KitTemplateDetail>(`/inventory/templates/${id}`).then((r) => r.data)

export const createTemplateApi = (body: { name: string; code: string }) =>
  api.post<KitTemplate>("/inventory/templates", body).then((r) => r.data)

/** Replaces the whole bill of materials — the API takes the full list, not a diff. */
export const setTemplateItemsApi = ({ id, lines }: {
  id: string
  lines: { item_id: string; required_qty: number }[]
}) => api.put<KitTemplateDetail>(`/inventory/templates/${id}/items`, lines).then((r) => r.data)

/* ── kits ──────────────────────────────────────────────────────────────── */

export const getKitsApi = (params: {
  location_id?: string
  holder_user_id?: string
  template_id?: string
  status?: string
  out_only?: boolean
} = {}) => api.get<KitListItem[]>("/inventory/kits", { params }).then((r) => r.data)

export const getKitApi = (id: string) =>
  api.get<KitDetail>(`/inventory/kits/${id}`).then((r) => r.data)

export const createKitApi = (body: {
  template_id: string
  label: string
  current_location_id: string
}) => api.post<KitDetail>("/inventory/kits", body).then((r) => r.data)

export const bulkCreateKitsApi = (body: {
  template_id: string
  location_id: string
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
  to_location_id?: string
  to_user_id?: string
  reason: MovementReason
  due_back_on?: string | null
  note?: string | null
}) => api.post<Movement>(`/inventory/kits/${id}/move`, body).then((r) => r.data)

export const getKitHistoryApi = (id: string) =>
  api.get<Movement[]>(`/inventory/kits/${id}/movements`).then((r) => r.data)

/** People a kit can be handed to. Separate from /admin/users, which is
 *  admin-only — ops needs a recipient picker, not user management. */
export const getHoldersApi = () =>
  api.get<{ id: string; full_name: string; roles: string[] }[]>("/inventory/holders")
    .then((r) => r.data)

/* ── stock and the ledger ──────────────────────────────────────────────── */

export const getStockApi = (params: { location_id?: string; item_id?: string } = {}) =>
  api.get<StockLevel[]>("/inventory/stock", { params }).then((r) => r.data)

export const moveStockApi = (body: {
  item_id: string
  qty: number
  reason: MovementReason
  from_location_id?: string
  from_kit_id?: string
  to_location_id?: string
  to_user_id?: string
  to_kit_id?: string
  note?: string | null
}) => api.post<Movement>("/inventory/stock/move", body).then((r) => r.data)

export const adjustStockApi = (body: {
  item_id: string
  location_id: string
  new_qty: number
  reason: string
}) => api.post<Movement>("/inventory/stock/adjust", body).then((r) => r.data)

export const getOverdueApi = () =>
  api.get<Movement[]>("/inventory/overdue").then((r) => r.data)

export const confirmMovementApi = (id: string) =>
  api.post<Movement>(`/inventory/movements/${id}/confirm`).then((r) => r.data)

/* ── instructor-facing ─────────────────────────────────────────────────── */

export const getMyKitsApi = () =>
  api.get<MyKit[]>("/inventory/my-kits").then((r) => r.data)
