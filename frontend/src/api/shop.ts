import { api } from "@/api/client";
import type {
  CatalogItemAvailable,
  ShopItem,
  ShopItemCreateInput,
  ShopItemUpdateInput,
  ShopOrder,
  ShopOrderFulfillInput,
} from "@/types/shop";

// ── Admin / Operations Shop Management ──────────────────────────────────────

export async function listShopItems(params?: {
  search?: string;
  is_published?: boolean;
}): Promise<ShopItem[]> {
  const { data } = await api.get<ShopItem[]>("/admin/inventory/shop", { params });
  return data;
}

export async function getAvailableCatalogItems(search?: string): Promise<CatalogItemAvailable[]> {
  const { data } = await api.get<CatalogItemAvailable[]>("/admin/inventory/shop/available-items", {
    params: { search },
  });
  return data;
}

export async function createShopItem(payload: ShopItemCreateInput): Promise<ShopItem> {
  const { data } = await api.post<ShopItem>("/admin/inventory/shop", payload);
  return data;
}

export async function getShopItem(id: string): Promise<ShopItem> {
  const { data } = await api.get<ShopItem>(`/admin/inventory/shop/${id}`);
  return data;
}

export async function updateShopItem(id: string, payload: ShopItemUpdateInput): Promise<ShopItem> {
  const { data } = await api.put<ShopItem>(`/admin/inventory/shop/${id}`, payload);
  return data;
}

export async function deleteShopItem(id: string): Promise<void> {
  await api.delete(`/admin/inventory/shop/${id}`);
}

// ── Shop Orders & Fulfillment ───────────────────────────────────────────────

export async function listShopOrders(params?: {
  status?: string;
  order_type?: string;
  search?: string;
}): Promise<ShopOrder[]> {
  const { data } = await api.get<ShopOrder[]>("/admin/inventory/shop/orders", { params });
  return data;
}

export async function getShopOrder(orderId: string): Promise<ShopOrder> {
  const { data } = await api.get<ShopOrder>(`/admin/inventory/shop/orders/${orderId}`);
  return data;
}

export async function fulfillShopOrder(
  orderId: string,
  payload: ShopOrderFulfillInput
): Promise<ShopOrder> {
  const { data } = await api.post<ShopOrder>(`/admin/inventory/shop/orders/${orderId}/fulfill`, payload);
  return data;
}
