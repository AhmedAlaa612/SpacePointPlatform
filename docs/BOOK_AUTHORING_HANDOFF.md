# SpacePoint Interactive Books — Developer Handoff

Technical specification for authoring, packaging, and integrating interactive HTML books into SpacePoint LMS.

---

## 1. Architecture Overview

- **Storage (`backend/app/services/lms/books_storage.py`):** Books are stored as unpacked versioned `.zip` bundles under `lms-books/{book_id}/v{bundle_version}/...` and cover images under `lms-book-covers/{book_id}/...` in a private Cloudflare R2 bucket (`R2_BOOKS_BUCKET`, `BOOKS_STORAGE_BACKEND=r2`), falling back to `STORAGE_BACKEND` in local/test environments.
- **Database (`backend/app/models/lms/book.py`):**
  - `LmsBook` — metadata, `outline` (JSONB), `profiles` (JSONB), `bundle_version`, `bundle_entry`, `access_mode` (`open` | `invite` | `paid`), `price_cents`, `is_published`.
  - `LmsBookEnrollment` — per-user access (`source`: `self` | `ops` | `program` | `purchase` | `invite_code`, `status`: `active` | `inactive`).
  - `LmsBookProgress` — cross-device `current_spread`, `current_chapter`, `active_profile`, `visited_spreads`, `stars`, `completion_pct`, `raw_state`.
  - `LmsBookExerciseResponse` — structured answers for quizzes, interactive labs, games, and notebook prompts.
- **Token-Gated Delivery (`backend/app/routers/lms/books.py`):**
  - `POST /lms/books/{book_id}/reader-session` checks access and issues a signed JWT (`create_book_token`, `type="book_reader"`) with `can_teacher` locked server-side to staff/instructor roles.
  - `GET /lms/books/read-bundle/{token}/{asset_path:path}` serves HTML documents with SpacePoint's runtime injected (`sp-book-config` meta tag, `__sp_runtime__/bridge.js`, `__sp_runtime__/reader.css`) while streaming relative sub-pages (`satkit.html`, `rocket.html`, JS/CSS/assets) directly under the same token prefix.
- **Default Cover Extraction (`extract_cover_page_html` in `backend/app/services/lms/books.py`):**
  - When no custom cover image is uploaded, `GET /lms/books/public/{book_id}/cover-page?v={version}` extracts the book's first/cover page (`data-book-cover`, `data-name="cover"`, `.cover`, or first `.page`/`.spread`), strips `<script>` and `on*` attributes, swaps `.brand` `"SPACE."` text for the inline SpacePoint white logo, and renders it inside a sandboxed `480×640` (`3:4`) `<BookCover />` iframe (`frontend/src/components/lms/BookCover.tsx`).

---

## 2. Bundle `.zip` Structure & Path Rules

```text
book-bundle/
├── index.html          # Entry HTML (or custom path matching `entry` in book.json)
├── book.json           # Manifest: metadata, profiles, and chapter/lesson outline
├── labs/               # Relative sub-pages / simulations (e.g. rocket.html, satkit.html)
│   └── sim.html
└── assets/             # Relative images, SVGs, CSS, JS
    └── diagram.svg
```

- **Relative paths only:** All internal links and asset references must be relative (`labs/sim.html`, `assets/diagram.svg`). Never use root-leading `/...` paths for bundle files, as bundles are served under `/lms/books/read-bundle/<token>/`.
- **Top-level folder unwrapping:** Uploading a `.zip` with a single enclosing root folder (e.g. `my-book/index.html`) automatically strips that prefix on ingestion.
- **Reserved prefix & limits:** Do not place files under `__sp_runtime__/`. Symlinks and `../` traversal paths are rejected (`400`). Max uncompressed size: `150 MB` / `1000` files (`MAX_ZIP_BYTES`, `MAX_ZIP_FILES`).

---

## 3. `book.json` Manifest Schema

```json
{
  "schema_version": 1,
  "slug": "orbital-systems-v1",
  "title": "Orbital Systems & CubeSat Engineering",
  "title_ar": "أنظمة المدارات وهندسة الأقمار الاصطناعية",
  "author": "SpacePoint",
  "entry": "index.html",
  "languages": ["en", "ar"],
  "default_profile": "all",
  "profiles": [
    {
      "key": "all",
      "label_en": "Full Book",
      "label_ar": "الكتاب الكامل",
      "subtitle_en": "All units and mission labs",
      "subtitle_ar": "جميع الوحدات والمختبرات",
      "default_lang": "en",
      "groups": []
    },
    {
      "key": "g10",
      "label_en": "Grade 10 Track",
      "label_ar": "مسار الصف العاشر",
      "subtitle_en": "Foundational orbital mechanics",
      "subtitle_ar": "أساسيات الميكانيكا المدارية",
      "default_lang": "en",
      "groups": ["u1", "u2", "m1"]
    }
  ],
  "outline": [
    {
      "key": "u1",
      "code": "U1",
      "part": "Physics Units",
      "title_en": "Frames of Reference & Orbit Velocity",
      "title_ar": "أطر الإسناد والسرعة المدارية",
      "lessons": [
        {
          "spread": "sp-u1-1",
          "title_en": "Why Satellites Stay Up",
          "title_ar": "لماذا تبقى الأقمار في المدار",
          "game_keys": ["orbit-speed-lab"]
        }
      ]
    }
  ]
}
```

- `outline[].lessons[].spread` should match the spread identifier in HTML so TOC clicks and LMS Program `book_chapter` tracking resolve accurately.
- `profiles[].groups` lists chapter keys included in that edition/track (`[]` = full book).

---

## 4. Injected Runtime & `window.SpacePointBook` API

HTML documents served through `/lms/books/read-bundle/{token}/...` automatically receive:
1. `<meta name="sp-book-config" content="...">` (`bookId`, `userId`, `version`, `canTeacher`, `initialState`, `visitedSpreads`, `startSpread`, `startChapter`, `startProfile`, `startTheme`, `startLang`).
2. `<script src="__sp_runtime__/bridge.js"></script>` (loaded early in `<head>`).
3. `<link rel="stylesheet" href="__sp_runtime__/reader.css">` (loaded at the end of `<head>`).

### JavaScript Bridge API (`window.SpacePointBook`)

```js
// Read server-verified context
const ctx = window.SpacePointBook?.getContext();
// { bookId, userId, canTeacher, lang, theme }

// Record spread visits & trigger progress sync
window.SpacePointBook?.setProgress({
  visitedSpreads: ["sp-u1-1", "sp-u1-2"],
  immediate: true,
});

// Report quiz, lab, game, or notebook answers
window.SpacePointBook?.reportExercise({
  chapter_key: "u1",
  exercise_key: "quiz:u1:q1",       // Stable unique key across bundle versions
  exercise_type: "quiz",            // "quiz" | "game" | "your_turn" | "notebook" | "lab"
  prompt_text: "What keeps a satellite in orbit?",
  answer_json: { selected: "Horizontal orbital velocity" },
  is_correct: true,                 // boolean | null
  score_stars: 1,                   // 0..3 (optional)
  max_stars: 1,                     // optional
});
```

### Parent Reader Commands (`postMessage`)

The React reader (`LearnBookReader.tsx`) sends `{ type: "SP_BOOK_CMD", cmd, value }` to the book iframe:
- `setTheme`: `"light"` | `"dark"`
- `setLang`: `"en"` | `"ar"`
- `setTeacher`: `boolean` *(must check `ctx.canTeacher === true`)*
- `setProfile`: `"<profile_key>"`
- `gotoSpread`: `"<spread_id>"`
- `gotoChapter`: `"<chapter_key>"`
- `prev` / `next`

---

## 5. Authoring & UI Conventions

- **First page = cover (`data-book-cover`):** Mark the opening cover container with `data-book-cover` (or `class="page cover"` / `data-name="cover"`) at a `3:4` (`480×640`) aspect ratio using self-contained HTML + inline SVG + CSS (renders without JS in catalog thumbnails).
- **2-column desktop / stacked mobile:** Pair reading (`.side-a`) and interactive simulation/exercises (`.side-b`) side by side above `900px`, stacking vertically in a single scroll below `900px`.
- **SpacePoint design tokens:** Flat `#18181B` / `#7C3AED` / `#FFFFFF` palette, `10px` radius, light & dark (`data-theme="light" | "dark"`) + RTL (`data-lang="en" | "ar"`) support, no AI/pedagogy taxonomy chips (`.btab`, `.bbadge`, `.cchip`, `.hatrow`), no emoji icons, and no hardcoded `"SPACE."` text branding.
- **Teacher mode lock:** Gate teacher notes/answers behind `window.SpacePointBook?.getContext()?.canTeacher === true`.

---

## 6. Reference Packager & Seeder

For SatKit-style standalone HTML bundles, `backend/scripts/package_satkit_book.py` extracts `outline` and `profiles` into `book.json`, and `backend/scripts/seed_satkit_book.py` seeds/updates `LmsBook` + uploads the bundle to R2 (`python -m scripts.seed_satkit_book`).
