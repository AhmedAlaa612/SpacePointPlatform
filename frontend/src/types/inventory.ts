/** Inventory domain (I1-4). Mirrors backend/app/schemas/inventory/. */

// Ops-editable data (`item_categories`), not a fixed set — see ItemCategoryDef.
export type ItemCategory = string
export type KitStatus = "working" | "damaged" | "retired" | "lost"
export type MovementReason =
  | "issue" | "return" | "transfer" | "refill" | "receive" | "writeoff" | "adjust" | "sold"

export interface Location {
  id: string
  name: string
  country: string
  is_active: boolean
  notes: string | null
  /** Where cohorts/sessions send instructors — the physical address and a
   *  map link, both optional. */
  address: string | null
  maps_url: string | null
  created_at: string | null
}

export interface Warehouse {
  id: string
  location_id: string
  location_name?: string | null
  name: string
  code?: string | null
  is_active: boolean
  address?: string | null
  notes?: string | null
  created_at?: string | null
}

export interface ItemCategoryDef {
  id: string
  name: string
  sort_order: number
}

export interface Item {
  id: string
  name: string
  category: ItemCategory
  returnable_default: boolean
  notes: string | null
  /** Shown to an instructor picking from the equipment shelf (B3). */
  description: string | null
  image_url: string | null
  /** Sized/variant merchandise only — e.g. "T-Shirt" + "L". Items sharing
   *  the same `variant_group` browse together in the catalogue/stock UI;
   *  stock, kit contents and custody still key on this item's own id,
   *  unchanged. Both null for anything that isn't a variant. */
  variant_group: string | null
  variant_label: string | null
}

export interface KitTemplate {
  id: string
  name: string
  /** Label prefix, e.g. SATKIT → SP-SATKIT-0001 */
  code: string
  is_active: boolean
}

export interface TemplateLine {
  item_id: string
  item_name: string
  required_qty: number
}

export interface KitTemplateDetail extends KitTemplate {
  items: TemplateLine[]
}

export interface KitShortage {
  item_id: string
  item_name: string
  required: number
  actual: number
  short_by: number
}

export interface KitContent {
  item_id: string
  item_name: string
  qty: number
}

export interface KitListItem {
  id: string
  template_id: string
  label: string
  status: KitStatus
  current_location_id: string
  current_warehouse_id: string
  current_holder_user_id: string | null
  notes: string | null
  template_code: string
  location_name: string
  warehouse_name: string
  holder_name: string | null
  shortage_count: number
}

export interface KitDetail extends Omit<KitListItem, "template_code" | "shortage_count"> {
  template_code: string
  template_name: string
  public_token: string
  contents: KitContent[]
  shortages: KitShortage[]
}

export interface Movement {
  id: string
  kit_id: string | null
  item_id: string | null
  qty: number | null
  from_location_id: string | null
  from_warehouse_id: string | null
  from_user_id: string | null
  from_kit_id: string | null
  to_location_id: string | null
  to_warehouse_id: string | null
  to_user_id: string | null
  to_kit_id: string | null
  session_id: string | null
  reason: MovementReason
  due_back_on: string | null
  note: string | null
  created_by: string
  created_at: string | null
  confirmed_by: string | null
  confirmed_at: string | null
  from_location_name?: string | null
  from_warehouse_name?: string | null
  from_user_name?: string | null
  to_location_name?: string | null
  to_warehouse_name?: string | null
  to_user_name?: string | null
}

export interface StockLevel {
  item_id: string
  item_name: string
  category?: string
  location_id: string
  location_name: string
  warehouse_id: string
  warehouse_name: string
  qty: number
}

export interface MyKit {
  id: string
  label: string
  template_name: string
  status: KitStatus
  location_name: string
  due_back_on: string | null
  shortage_count: number
  /** Where "mark returned" defaults to — the session it was last issued
   *  for, if there was one. Null only when that can't be resolved either. */
  default_return_warehouse_id: string | null
  default_return_warehouse_name: string | null
}

export interface MyHeldItem {
  item_id: string
  item_name: string
  variant_group: string | null
  variant_label: string | null
  qty: number
  due_back_on: string | null
  default_warehouse_id: string | null
  default_warehouse_name: string | null
}
