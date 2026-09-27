export interface ShopWarehouseStock {
  warehouse_id: string;
  warehouse_name: string;
  warehouse_code?: string | null;
  qty: number;
}

export interface ShopItem {
  id: string;
  item_id: string;
  slug: string;
  display_name: string;
  subtitle?: string | null;
  description?: string | null;
  price_aed: number | string;
  compare_at_price_aed?: number | string | null;
  cover_image_url?: string | null;
  gallery_images: string[];
  is_published: boolean;
  is_preorder_enabled: boolean;
  preorder_message: string;
  display_order: number;
  catalog_item_name: string;
  catalog_item_category: string;
  total_stock: number;
  warehouse_breakdown: ShopWarehouseStock[];
  stock_status: "in_stock" | "pre_order";
  created_at: string;
  updated_at: string;
}

export interface CatalogItemAvailable {
  id: string;
  name: string;
  code: string;
  category: string;
  unit?: string;
  total_stock: number;
  warehouse_breakdown: ShopWarehouseStock[];
}

export interface ShopItemCreateInput {
  item_id: string;
  slug: string;
  display_name: string;
  subtitle?: string | null;
  description?: string | null;
  price_aed: number;
  compare_at_price_aed?: number | null;
  cover_image_url?: string | null;
  gallery_images?: string[];
  is_published: boolean;
  is_preorder_enabled: boolean;
  preorder_message?: string;
  display_order?: number;
}

export interface ShopItemUpdateInput extends Partial<ShopItemCreateInput> {}

export interface ShopOrderItem {
  id: string;
  shop_item_id: string;
  item_name: string;
  unit_price_aed: number | string;
  quantity: number;
  is_preorder: boolean;
}

export interface ShopOrder {
  id: string;
  order_number: string;
  customer_name: string;
  customer_email: string;
  customer_phone?: string | null;
  shipping_address: Record<string, any>;
  status: string;
  order_type: string;
  total_amount_aed: number | string;
  currency: string;
  stripe_payment_intent_id?: string | null;
  stripe_checkout_session_id?: string | null;
  fulfilled_warehouse_id?: string | null;
  fulfilled_warehouse_name?: string | null;
  fulfilled_at?: string | null;
  fulfillment_notes?: string | null;
  created_at: string;
  items: ShopOrderItem[];
}

export interface ShopOrderFulfillInput {
  warehouse_id: string;
  notes?: string;
}
