export type ShopOrderStatus =
  | "pending_payment"
  | "paid"
  | "fulfilled"
  | "failed"
  | "expired"

export interface ShopItem {
  id: string
  item_id: string | null
  slug: string
  display_name: string
  subtitle: string | null
  description: string | null
  price_aed: number
  compare_at_price_aed: number | null
  cover_image_url: string | null
  gallery_images: string[]
  is_published: boolean
  is_preorder_enabled: boolean
  preorder_message: string
  display_order: number
  created_at: string
  updated_at: string
}

export type ShopItemCreate = Pick<
  ShopItem,
  | "slug"
  | "display_name"
  | "subtitle"
  | "description"
  | "price_aed"
  | "compare_at_price_aed"
  | "cover_image_url"
  | "gallery_images"
  | "item_id"
  | "is_published"
  | "is_preorder_enabled"
  | "preorder_message"
  | "display_order"
>

export type ShopItemUpdate = Partial<
  Pick<
    ShopItem,
    | "slug"
    | "display_name"
    | "subtitle"
    | "description"
    | "price_aed"
    | "compare_at_price_aed"
    | "cover_image_url"
    | "gallery_images"
    | "item_id"
    | "is_published"
    | "is_preorder_enabled"
    | "preorder_message"
    | "display_order"
  >
>

export interface ShopOrderItem {
  id: string
  shop_item_id: string
  item_name: string
  unit_price_aed: number
  quantity: number
  is_preorder: boolean
}

export interface ShopOrder {
  id: string
  order_number: string
  customer_name: string
  customer_email: string
  customer_phone: string | null
  shipping_address: Record<string, string>
  status: ShopOrderStatus | string
  order_type: string
  total_amount_aed: number
  currency: string
  stripe_checkout_session_id: string | null
  fulfilled_warehouse_id: string | null
  fulfilled_at: string | null
  fulfillment_notes: string | null
  created_at: string
  items: ShopOrderItem[]
}
