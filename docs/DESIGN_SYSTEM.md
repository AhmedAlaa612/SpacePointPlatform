# SpacePoint Design System

> **Source of Truth** for UI/UX design tokens, layout principles, and styling rules across SpacePoint Portal and LMS.
> Initiated: November 2026.

---

## 1. Core Principles

1. **No Gradients:** Solid, flat colors only. Strictly forbidden to use gradient fills, gradient text, or gradient borders.
2. **No Emojis:** Never use emojis in UI elements, status tags, buttons, or headers. Use clean SVG vector icons (Lucide-style) or clear typographic labels.
3. **No In-UI Explanatory Clutter:** Do not add helper text, explanatory paragraphs, or microcopy next to buttons or inputs explaining how they work or their rules. The interface must be self-evident, clean, and confident.
4. **Large, High-Legibility Typography:** Clean sans-serif font stack (Inter, Geist, or system sans) with clear hierarchy, large readable headers, and strong optical contrast.
5. **Direct-on-Background Forms:** When creating or editing an item, place form fields and text directly on the canvas background—avoid nesting cards inside cards.
6. **No Text Truncation (`...`):** Never use `truncate`, `text-ellipsis`, or `line-clamp` that cuts off labels, titles, or metadata with `...` (`text-overflow: ellipsis`). Size grids cleanly or allow natural line wrapping so every label remains readable in full.

---

## 2. Color System (Strict Palette)

The color palette is strictly restrained to Purple, Black, White, and Grayscale. The only permitted exceptions are Rose (destructive/critical alerts) and Green (active/success alerts). **Blue, sky, cyan, yellow, amber, orange, and teal colors (e.g., Tailwind `sky-*`, `blue-*`, `amber-*`, `teal-*`) must NEVER be used**—including for info banners, sync badges, or status cards.

| Token | Hex / Value | Usage |
|---|---|---|
| **Purple Primary** | `#7C3AED` / `#6D28D9` | Primary action buttons, active tabs, focused states, brand accents |
| **Purple Dark** | `#4C1D95` | Pressed buttons, deep brand emphasis |
| **Purple Light / Tint** | `#F5F3FF` (Light) / `#2E1065` (Dark) | Subtle active chip backgrounds, selected row highlights |
| **Black & Slate** | `#09090B` / `#18181B` / `#27272A` | Backgrounds, primary text, high-contrast borders |
| **White & Neutral** | `#FFFFFF` / `#F4F4F5` / `#E4E4E7` | Card backgrounds (light), surfaces, borders, secondary text |
| **Alert — Rose** | `#E11D48` / `#BE123C` / `#FFE4E6` | Critical alerts, error badges, destructive actions, cancel buttons |
| **Alert — Green** | `#16A34A` / `#15803D` / `#DCFCE7` | Success badges, active/running status indicators |

---

## 3. Geometry & Corner Radii

- **Corner Radius: Strictly `10px` (`rounded-[10px]` in Tailwind)**
- Applies uniformly to:
  - Cards and surface containers
  - Buttons (primary, secondary, icon buttons)
  - Text inputs, textareas, and select menus
  - Status chips, badges, and pill tags
  - Modals, drawers, and popovers

---

## 4. Layout & Information Architecture

- **Un-nested Creation Flows:** Creation forms and drawers place labels, inputs, and actions directly onto the background without enclosing them in inner cards or boxes.
- **Hierarchical Grouping:** Master items (e.g. Programs) anchor their child executions (e.g. Cohorts) directly within their scope, while preserving rapid operational filtering.
- **Action Density:** Primary action clearly situated; secondary actions grouped; no redundant advisory copy.
- **No Dot-Separated Metadata Strings:** Never concatenate multiple metadata values with middle dots (`·`). Render each field as a spaced icon-labelled inline item or a distinct chip.
- **Never Cut Off Text with Ellipsis:** Never clip KPI card titles, table column headers, or identity strings with `...` (`truncate`). Adjust grid columns, spacing, or line wrapping instead.
