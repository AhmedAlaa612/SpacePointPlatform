# Inventory — Stock Counts, Kit Counts & Fast-Follows: Testing Handoff

Back to [`HANDOFF.md`](./HANDOFF.md). Written 2026-08-02 for whoever (human or agent) verifies
this end to end — everything below was built and unit/type-checked, but **never opened in a
browser**. That's the one thing this handoff asks you to do.

## What this covers

Two passes, same day, same root cause (see the original review — not committed to this repo,
ask the operator if you need the full text): *"every inventory write goes through one row at a
time, through one narrow door, and the doors that would make it easy were built but never
opened."*

**Pass 1 — the two highest-leverage items:**
1. **Bulk stock counts.** `POST /inventory/stock/adjust-bulk` (`backend/app/routers/inventory/stock.py`)
   loops the existing `adjust_stock()` in one transaction. Frontend: `StockCountModal.tsx` — one
   item, every active warehouse, one grid, one reason, replacing the old single-warehouse
   `AdjustModal`/`ItemAdjustModal` (both deleted).
2. **Count a kit directly.** `POST /inventory/kits/{kit_id}/count` (new `count_kit()` in
   `backend/app/services/inventory/movements.py`) — the first real caller of the kit-write path
   `move()` already supported (`to_kit_id` with no shelf) but nothing in the UI ever used.
   Gated `require_storekeeper` as a deliberate, narrow exception to this router's usual
   `require_operations` — a storekeeper standing in front of an open box can now say what's in
   it. Frontend: a "Count this kit" button + grid on `KitDetail.tsx`.

**Pass 2 — fast-follows (everything except P3, per operator instruction):**
- **P2** — `Stock.tsx` rebuilt item-first: one card per item (total across warehouses as the
  headline, a breakdown line underneath, truncated past 3 with "+N more"), with category,
  location, warehouse, "out of stock" and "not stocked anywhere" filters. A warehouse filter
  swaps the headline number and drops cards with nothing there rather than changing what a card
  *is*.
- **P4** — `WarehouseStockTakeModal.tsx`, new: the transpose of P1 — one warehouse, every item,
  search + category filter + "only items already stocked here" toggle. Same `adjust-bulk`
  endpoint. Reachable from Stock's new "Stock take" button.
- **P6** — copy only. `Catalog.tsx`'s Locations/Warehouses tabs each gained one explanatory
  sentence (location = city/site, warehouse = a store within it), and the New Location
  placeholder changed from `"Main Warehouse, Dubai, Egypt…"` (taught the wrong model) to
  `"Dubai, Abu Dhabi, Cairo…"`.
- **P8** — `POST /inventory/kits` gained a `complete: bool` field. When true, seeds the new
  kit's contents from its template's BOM via real `receive` movements (unlike
  `bulk_create_kits`' existing `complete` flag, which inserts `KitItem` rows directly with no
  ledger entry — that one's a fleet backfill, this one's a single real event worth an audit
  trail). **No frontend calls single-kit `createKitApi` today** — the only kit-creation UI is
  `Kits.tsx`'s `BulkCreateModal`, which already had this checkbox before today. The backend
  change is real and tested, but there is nothing to click to exercise it directly; using bulk
  create with count=1 is the equivalent path today.
- **P9** — `Fulfilment.tsx`: when a kit's `fixable_now === 0`, the dead disabled "Fulfil" button
  is replaced with **"Count this kit"** (links straight to the kit's page) and **"Add to
  shelf"** (new `AddToShelfModal`, prefilled with exactly the missing items at exactly the
  quantity that closes the gap, same `adjust-bulk` endpoint). Separately, `FulfilModal` gained a
  **"Pull from"** warehouse picker — `fulfil_kit()` always accepted a `from_warehouse_id`
  override, the UI just never exposed it; switching warehouses refetches that shelf's stock so
  the caps stay honest.
- **P10** — `MoveStockModal.tsx`, new: two modes (tab toggle) over the same `moveStockApi` —
  **Transfer** (item + qty + from warehouse + to warehouse) and **Receive a delivery** (item +
  qty + destination warehouse, reason `receive` instead of the `adjust` it was being faked as
  before). Supports multiple item lines per save; each line still fires its own movement call
  (`move()` has no bulk variant, unlike `adjust_stock()`). Receiving straight into a *kit* is
  intentionally left to "Count this kit" (P7) rather than duplicated here.

**Deliberately not done:** **P3** (auto-resolve the single-warehouse case everywhere, the way
`_resolve_effective_warehouse` already does for cohorts/sessions) — explicitly excluded by the
operator for this pass, not an oversight.

**Pass 3 — lightweight size/variant grouping (operator ask: "T-Shirt S/M/L/XL shouldn't be 5
unrelated catalogue rows"):**
- **Schema**: `items` gained two nullable columns — `variant_group` (e.g. `"T-Shirt"`) and
  `variant_label` (e.g. `"L"`). Migration `d1e4c73f0038`. **Deliberately the lightweight version**,
  not a real e-commerce product/variant split: `stock_levels`, `kit_items` and `movements` are
  completely untouched — every variant is still its own full `Item` row with its own stock and
  custody, exactly as before. This is display/browsing metadata only, modeled the same way
  `items.category` already is (plain string, no FK table — see that model's own docstring for
  why, and the migration's docstring for why this follows suit rather than building a full
  variant table).
- **Backend**: `ItemCreate`/`ItemUpdate`/`ItemOut` (`schemas/inventory/catalog.py`) carry both
  fields. `routers/inventory/catalog.py`'s new `_normalize_variant_fields()` blanks
  `variant_label` whenever `variant_group` is cleared or absent (a label means nothing without a
  group), and turns empty-string input into `NULL` either way. `HeldItemOut`
  (`schemas/inventory/custody.py`) and `MyHeldItemOut` (`schemas/inventory/holdings.py`) both
  gained the same two fields, sourced from `held_by_user()`
  (`services/inventory/custody.py`) — so custody/holdings records carry the variant along, even
  though **the ledger was already correct on this point**: each size is its own `Item.id` with
  its own distinct `name` (e.g. `"T-Shirt L"`), so "which variant did they take" was always
  answerable from `item_name` alone. This just adds a structured field instead of relying on
  parsing the name.
- **Frontend**: `Item` type, `MyHeldItem` type, `createItemApi` gained the two fields.
  `ItemModal` (`Catalog.tsx`) gained "Sized/variant of" (free-text with a datalist of existing
  group names — typing a new one creates it on save, no separate "manage groups" screen) and
  "Size / variant label" (disabled until a group is set). **New `VariantsModal.tsx`**: opened
  from a group card, lists every variant with its per-location breakdown (reusing the same
  `getItemsApi()`/`getStockApi()` data both pages already fetch, filtered client-side — no new
  read endpoint) and an "Edit counts" button per variant that opens the existing
  `StockCountModal` unchanged. `Catalog.tsx`'s Components tab and `Stock.tsx`'s item cards both
  now group same-`variant_group` items into one card (photo/category from one representative,
  total summed across every size, a "N sizes" badge, a "View sizes"/"Edit" button opening
  `VariantsModal` instead of the single-item flow). Out-of-stock/not-stocked-anywhere/location/
  warehouse filters on `Stock.tsx` all roll up across the whole group, not per size.
  `MyHoldings.tsx` shows the variant label as a small badge next to the item name.
- **Not touched**: `SessionEquipmentPanel.tsx` and the equipment pickup flow (`equipment.py`) —
  out of scope for this ask (that's kit-adjacent gear, not merch/custody) and those files already
  had unrelated uncommitted changes from before this session. The admin-side "who's holding
  what" endpoint (`GET /inventory/merch/held/{user_id}`) has **zero frontend call sites today**
  (confirmed by grep) — same as `moveStockApi` was before P10 and single-kit `createKitApi`
  still is after P8 — so the backend fields are real and tested but there's no existing page to
  see them on except `MyHoldings.tsx` (the instructor's own view, which was updated).

**⚠️ Migration required before browser-testing anything in Pass 3 (or Catalog's item form at
all, once you touch it):** `d1e4c73f0038` has been applied to `spacepoint_test` only — running
the test suite exposed this (item creation 500'd with `UndefinedColumnError: column
"variant_group" of relation "items" does not exist` until the test DB was migrated). **It has
NOT been applied to `spacepoint_dev`.** Running `alembic upgrade head` against dev will also
pick up whatever migrations the concurrent session/cohort pass has queued — deliberately left
for the operator to do once, at a moment that doesn't collide with that other work, rather than
this handoff or an agent doing it unilaterally against a database someone else may be using
live. **Do not open the Catalogue's item form or Stock page against `spacepoint_dev` until
someone has run this.**

## Environment

- Dev clone: `spacepoint-platform-dev`, branch `v2-dev`. **The working tree has substantial
  unrelated uncommitted changes from a separate, concurrent session/cohort UX pass** — do not
  be alarmed by a large `git status`; none of it overlaps the files listed above (verified
  before starting). If you need a clean diff of just this work, `git stash` isn't safe here —
  ask the operator before doing anything that touches files outside the list above.
- Backend: `cd backend && .venv\Scripts\uvicorn.exe app.main:app --port 8000` (Python 3.13 venv
  already present at `backend/.venv`). Postgres 17 on port **5433**, DB `spacepoint_dev`,
  credentials in `backend/.env` (gitignored).
- Frontend: `cd frontend && npm run dev` — probe `localhost:5173`, not `127.0.0.1` (Vite binds
  IPv6 in this environment).
- **Login:** `dev-admin@spacepoint.ae` / `devadmin123`. `admin` passes every role guard —
  **do not test only as admin**. This codebase has a documented incident (`HANDOFF.md` §8,
  gotcha 17) where a storekeeper-only endpoint 403'd for two days because it was only ever
  walked as admin. For the storekeeper-gated pieces here (adjust-bulk, count-kit), create or
  promote **two separate test accounts** via Admin → Users: one with only the `storekeeper`
  role, one with only `operations` — not one account with both, or you can't tell which guard
  is actually firing.
- Seed data (`python scripts/seed_inventory.py`, idempotent) gives 5 locations, a ~50-item
  catalogue, and the SatKit BOM — but as of the original review, only 2 of those 50 items had
  any stock count anywhere, and all 4 existing kits were short on most/all of their parts list.
  That's the actual condition this work is meant to fix, not a setup error — expect an empty
  Stock page and a full Fulfilment queue on first look.

## Already verified (don't re-do)

- Backend: `.venv\Scripts\python.exe -m pytest tests/routers/inventory/ tests/services/inventory/ -q`
  → **185 passed**, 0 failed. Includes new tests for `adjust-bulk` (partial-skip-on-409),
  `count_kit` (all four refill/receive/adjust branches), the storekeeper carve-out on
  `/kits/{id}/count`, `create_kit`'s `complete` flag, and Pass 3's variant-group round trip,
  the label-blanks-without-a-group rule, and `held_by_user` carrying the variant through.
- Frontend: `npx tsc --noEmit` → clean, 0 errors, after every change across all three passes.
- Full backend suite (`pytest` from `backend/`, no filter): **632 passed, 5 failed, 5 errors** —
  all five failures/errors are in `tests/services/sessions/test_staffing.py`,
  `tests/routers/sessions/test_staffing_router.py`, `test_public_registration.py`,
  `test_registration_desk.py`. **Unrelated to this work** — nothing here touches sessions,
  staffing, or registration code; these come from the concurrent session/cohort pass mentioned
  above being mid-edit. Don't chase them as regressions from this handoff; do flag to the
  operator if they're still red once that other pass lands.
- One pre-existing test needed a one-line update, not a behavior change: `test_custody_and_public.py::test_issuing_and_returning_a_vest`
  asserted an exact dict on `GET /inventory/merch/held/{id}` that didn't yet include the two new
  `variant_group`/`variant_label: None` keys — updated to match, no logic changed.

## What's NOT done — the actual point of this handoff

**Nothing in either pass has been exercised in a real browser.** Pytest proves the service
logic; `tsc` proves it compiles. Neither proves the UI wires up correctly, that a modal opens
where it should, that a filter actually narrows the grid, or that the numbers shown match what
the API returns. Please walk through all of the following, logged in as the appropriate role:

### 1. Bulk stock counts (storekeeper AND operations)
- Stock page, an item with zero counts anywhere → "Record a count" → set quantities in **two
  different warehouses** in one save, one reason → confirm both `stock_levels` rows appear and
  `GET /inventory/movements` shows two rows carrying that reason.
- Same item's card → "Edit counts" → confirm it opens pre-filled with what you just entered,
  including "was N" against each warehouse and blank against ones you didn't touch.
- Catalogue → Components tab → a component's "Adjust" button → confirm it opens the *same*
  component, and that leaving all fields unchanged and hitting Save is refused ("change at
  least one warehouse's count"), not silently accepted.
- Confirm a location with only one warehouse shows just the location name (no second dropdown),
  and Dubai (or whichever location has two) shows both.

### 2. Stock take (P4)
- Stock page → "Stock take" → pick a warehouse with nothing stocked yet → search/filter by
  category → set several items' counts in one save → confirm the Stock page's cards now show
  that warehouse in their breakdown line.
- Toggle "Only items already stocked here" and confirm the list actually narrows once something
  is stocked.

### 3. Stock page filters (P2)
- With counts entered in ≥2 warehouses for one item: confirm the card shows a **total** as the
  big number and a breakdown line underneath (e.g. `Dubai 30 · Abu Dhabi 12`).
- Select a warehouse filter: confirm the headline number changes to just that warehouse's count,
  and any card with nothing there disappears entirely.
- Toggle "Out of stock": confirm it shows only items with a real row summing to 0 (not items
  that have never been stocked at all).
- Toggle "Not stocked anywhere": confirm it shows the inverse — items with literally zero rows
  — and that the two toggles are mutually exclusive in practice.

### 4. Count a kit directly (P7 — as storekeeper)
- Open a kit with all-zero or partial contents → "Count this kit" → **leave the shelf checkbox
  unticked**, set some quantities, save → confirm kit contents update, `stock_levels` is
  **untouched**, and the kit's history shows `receive`.
- Same kit → count again, **tick the checkbox**, increase a quantity → confirm the kit's own
  warehouse shelf decrements by the difference and the movement reason is `refill`.
- Decrease a quantity with the checkbox **unticked** → confirm the movement reason is `adjust`
  and, again, no shelf is touched.
- As a storekeeper-only account: confirm `/inventory/kits` (the list) and the kits catalogue
  still 403, but `POST /inventory/kits/{id}/count` succeeds — this is the one deliberate hole in
  that role's fence.

### 5. Fulfilment dead-end exits + source warehouse (P9)
- Find (or create, via a session count) a kit with `fixable_now === 0` → confirm there is no
  disabled button, just **"Count this kit"** (navigates to the kit page) and **"Add to
  shelf"**.
- "Add to shelf" → confirm every line is prefilled with *current + exactly what's short* → save
  → confirm the kit either becomes fixable or drops out of the queue if that closed it.
- On a kit that **is** fixable now: open "Fulfil" → change "Pull from" to a different warehouse
  → confirm the "N there" numbers and the input caps update to that warehouse's stock, not the
  kit's own → submit → confirm the movement's `from_warehouse_id` is the one you picked, not the
  kit's default.

### 6. Transfer / receive (P10)
- Stock page → "Transfer / receive" → **Transfer** tab: move an item between two warehouses,
  confirm both `stock_levels` rows update and the movement reason is `transfer`.
- **Receive** tab: receive an item into a warehouse with a note (e.g. a PO number) → confirm the
  movement reason is `receive`, not `adjust` — this was the specific thing being faked before.
- Add a second line before saving → confirm two separate movements are written, not one.

### 7. Copy (P6)
- Catalogue → Locations tab and Warehouses tab: confirm the new explanatory sentence reads
  sensibly in place. New Location modal: confirm the placeholder now reads
  `"Dubai, Abu Dhabi, Cairo…"`.

### 8. Size/variant grouping (Pass 3)
**Run `alembic upgrade head` against `spacepoint_dev` first (see the ⚠️ above) or every step
here 500s.**
- Catalogue → Components → "Add Component" → create "T-Shirt S" with "Sized/variant of" =
  `T-Shirt`, "Size / variant label" = `S`. Repeat for M/L (the datalist should now suggest
  "T-Shirt" once it exists). Confirm the three collapse into **one card** reading "T-Shirt · 3
  sizes" instead of three separate cards.
- Click that card's "View sizes" → confirm a modal lists S/M/L, each with its own per-location
  breakdown line and an "Edit counts" button. Use "Edit counts" on one size → confirm it opens
  the ordinary `StockCountModal` for that one variant (not the others) and saving updates only
  that size's total in the list underneath.
- Stock page: confirm the same grouping appears there (one "T-Shirt" card, total across every
  size × every warehouse). Toggle the warehouse filter and confirm the group's total updates to
  just that warehouse's sum across sizes. Stock a size in only one warehouse and confirm "Not
  stocked anywhere" only hides it once **every** size has zero rows everywhere, not just one.
- Edit an existing variant's item and clear the "Sized/variant of" field → save → confirm it
  becomes its own standalone card again (ungrouped) and the label field cleared with it.
- Issue a T-shirt size to an instructor (via whatever custody path exists/`POST
  /inventory/merch/issue` directly if no UI) → open that instructor's `MyHoldings.tsx` (or `GET
  /inventory/my-merch`) → confirm the size shows as a small badge next to the item name, not just
  a generic "T-Shirt".
- Confirm `stock_levels`/`kit_items`/`movements` never gained a `variant_group`/`variant_label`
  column and every read still keys on the specific item id — this was meant to be purely additive
  metadata, not a schema change to how counting works.

### 9. Regression pass
- Confirm the original session-loop flows this shares services with still work: an
  instructor's post-session kit check (`record_check`), the storekeeper's stock page (`GET
  /inventory/stock`, `/overdue`), and that a storekeeper still cannot reach the catalogue, kit
  list, kit create/edit, or kit templates.
- Confirm an item with no `variant_group` (the overwhelming majority of the ~50-item seeded
  catalogue) still renders exactly as before — single card, no "sizes" badge, "Adjust"/"Edit"
  as today.

## If something's wrong

File:line references for every change are in the two plan documents this session produced
(ask the operator — they're in `~/.claude/plans/`, not committed here). The design rationale
for the trickier bits (why `count_kit()` needs no schema/`move()` changes, why P8's `complete`
flag differs from bulk-create's, why storekeeper gets a router-level carve-out instead of a
blanket permission widen) is in the code comments at each of those call sites — read those
before assuming something is a bug rather than a documented tradeoff.
