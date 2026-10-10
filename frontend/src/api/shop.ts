import { api } from "./client"
import type { ShopItem, ShopItemCreate, ShopItemUpdate, ShopOrder } from "@/types/shop"

// ── Catalogue ─────────────────────────────────────────────────────────────────

export const getShopItems = () =>
  api.get<ShopItem[]>("/admin/shop/items").then((r) => r.data)

export const createShopItem = (payload: ShopItemCreate) =>
  api.post<ShopItem>("/admin/shop/items", payload).then((r) => r.data)

export const updateShopItem = (id: string, payload: ShopItemUpdate) =>
  api.put<ShopItem>(`/admin/shop/items/${id}`, payload).then((r) => r.data)

export const deleteShopItem = (id: string) =>
  api.delete(`/admin/shop/items/${id}`).then((r) => r.data)

// ── Orders ────────────────────────────────────────────────────────────────────

export const getShopOrders = (status?: string) =>
  api.get<ShopOrder[]>("/admin/shop/orders", { params: status ? { status } : {} }).then((r) => r.data)

export const getShopOrder = (id: string) =>
  api.get<ShopOrder>(`/admin/shop/orders/${id}`).then((r) => r.data)

export const fulfillShopOrder = (id: string, payload: { warehouse_id?: string | null; notes?: string | null }) =>
  api.post<ShopOrder>(`/admin/shop/orders/${id}/fulfill`, payload).then((r) => r.data)
