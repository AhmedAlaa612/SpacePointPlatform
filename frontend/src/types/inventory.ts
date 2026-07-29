/** Inventory domain (I1-4). Mirrors backend/app/schemas/inventory/. */

export type ItemCategory = "sensor" | "board" | "tool" | "mechanical" | "merch" | "other"
export type KitStatus = "working" | "damaged" | "retired" | "lost"
export type MovementReason =
  | "issue" | "return" | "transfer" | "refill" | "receive" | "writeoff" | "adjust" | "sold"

export interface Location {
  id: string
  name: string
  country: string
  is_active: boolean
  notes: string | null
  created_at: string | null
}

export interface Item {
  id: string
  name: string
  category: ItemCategory
  /** Excluded from completeness entirely — never makes a kit look incomplete. */
  is_consumable: boolean
  returnable_default: boolean
  notes: string | null
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
  is_consumable: boolean
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
  current_holder_user_id: string | null
  notes: string | null
  template_code: string
  location_name: string
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
  from_user_id: string | null
  from_kit_id: string | null
  to_location_id: string | null
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
}

export interface StockLevel {
  item_id: string
  item_name: string
  location_id: string
  location_name: string
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
}
