# SpacePoint Interactive Books — Authoring Spec

Build a **standalone-first** interactive HTML book `.zip` (`index.html`, `book.json`, and relative assets/labs) that opens directly in any browser and plugs cleanly into the SpacePoint LMS Reader.

---

## 1. Bundle `.zip` Structure & Rules

```text
my-book/                # Optional single wrapper folder (or files directly at zip root)
├── index.html          # Entry HTML (matches `entry` in book.json)
├── book.json           # Metadata, edition profiles, and chapter/lesson outline
├── labs/               # Optional relative sub-pages / simulations
└── assets/             # Optional relative images, SVGs, CSS, JS
```

- **Relative paths only** (`labs/sim.html`, `assets/diagram.svg`) — never leading `/...` or `../`.
- **Reserved path:** Do not create `__sp_runtime__/` (injected by SpacePoint).
- **Limits:** No symlinks; max `150 MB` uncompressed / `1000` files.
- **Self-contained:** Bundle styles/scripts/SVGs locally so lessons and the cover work offline.

---

## 2. `book.json` Manifest

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
      "subtitle_en": "All units and labs",
      "subtitle_ar": "جميع الوحدات والمختبرات",
      "default_lang": "en",
      "groups": []
    },
    {
      "key": "g10",
      "label_en": "Grade 10 Track",
      "label_ar": "مسار الصف العاشر",
      "subtitle_en": "Core orbital mechanics",
      "subtitle_ar": "أساسيات الميكانيكا المدارية",
      "default_lang": "en",
      "groups": ["u1", "u2"]
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

- Every `outline[].lessons[].spread` must match a `.spread[data-name="..."]` in `index.html`.
- Every `outline[].key` must match `.spread[data-ch="..."]`.
- `profiles[].groups` lists `outline[].key` chapters (`[]` = full book).

---

## 3. Minimal HTML Structure (`index.html`)

```html
<!doctype html>
<html lang="en" data-lang="en" data-theme="light" data-teacher="0">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Book Title</title>
  <style>
    html[data-lang="en"] .ar,
    html[data-lang="ar"] .en { display: none; }
    html:not([data-teacher="1"]) .tn,
    html:not([data-teacher="1"]) .tcard { display: none; }
    html[data-sp-embedded="1"] .bar { display: none; }

    .stage { display: flex; flex-direction: column; height: 100dvh; }
    .book { position: relative; flex: 1; }
    .page { display: none; }
    .page.show { display: flex; flex-direction: column; }
    .pin { flex: 1; overflow-y: auto; padding: 32px; display: flex; flex-direction: column; gap: 16px; }
  </style>
</head>
<body>
  <!-- Standalone toolbar (auto-hidden when embedded in LMS via html[data-sp-embedded="1"]) -->
  <header class="bar">...</header>

  <main class="stage">
    <div class="book closed">
      <!-- Cover spread: renders with JS off at 480x640 for catalog cards -->
      <section class="spread" data-name="cover">
        <div class="page cover show" data-book-cover>
          <div class="pin">
            <div class="brand">SPACE.</div>
            <div>
              <h1><span class="en">Orbital Systems</span><span class="ar" dir="rtl">أنظمة المدارات</span></h1>
              <p class="sub"><span class="en">Hands-on CubeSat Labs</span><span class="ar" dir="rtl">مختبرات الأقمار الاصطناعية</span></p>
            </div>
            <svg viewBox="0 0 360 220" aria-hidden="true"></svg>
          </div>
        </div>
      </section>

      <!-- Lesson spread: side-a (Reading) + side-b (Lab / Exercises / Notebook) -->
      <section class="spread" data-name="sp-u1-1" data-ch="u1" data-ten="Why Satellites Stay Up" data-tar="لماذا تبقى الأقمار في المدار">
        <article class="page side-a">
          <div class="pin">
            <h2><span class="en">Why Satellites Stay Up</span><span class="ar" dir="rtl">لماذا تبقى الأقمار في المدار</span></h2>
            <p class="en">Explanation...</p>
            <p class="ar" dir="rtl">الشرح...</p>
            <aside class="tn"><strong class="en">Teacher Note:</strong> <span class="en">Key misconception...</span></aside>
          </div>
        </article>

        <article class="page side-b">
          <div class="pin">
            <div class="eq">v = sqrt(GM / r)</div>
            <label for="nb-u1-1"><span class="en">Reflection</span><span class="ar" dir="rtl">تأمل</span></label>
            <textarea id="nb-u1-1" data-nb rows="4"></textarea>
          </div>
        </article>
      </section>
    </div>

    <footer class="pager">
      <button id="prev" type="button">Previous</button>
      <span id="pn">1 / 2</span>
      <button id="next" type="button">Next</button>
    </footer>
  </main>
</body>
</html>
```

- **Cover (`data-book-cover`):** Style in `<head>` CSS + inline `<svg>` so it renders cleanly at `480×640` with JS disabled. Never put cover buttons (`.cover .btn` / `[data-goto]`), and never hardcode footer `"SPACE."` text branding (use `.brand` or omit).
- **Active spread:** Put `.show` on both `.page.side-a` and `.page.side-b` of the active spread (and `.book.closed` on `cover`).
- **Teacher notes (`.tn` / `.tcard`):** Hidden automatically for students (`canTeacher === false`).
- **Notebooks (`[data-nb]`):** `<textarea id="..." data-nb>` with a matching `<label for="...">` syncs automatically.

---

## 4. Standalone-First Runtime Bridge (`window.SpacePointBook`)

- **Works standalone first:** Open `index.html` directly in a browser without any server. All `window.SpacePointBook?.` calls below use optional chaining (`?.`), so they are safe no-ops standalone and automatically activate when SpacePoint injects `window.SpacePointBook` inside the LMS.
- **Standalone controls:** Your `.bar` toolbar works standalone and is auto-hidden inside the LMS (`html[data-sp-embedded="1"] .bar { display: none }`).
- **Teacher toggle:** When `window.SpacePointBook` exists, lock teacher mode to `window.SpacePointBook.getContext().canTeacher === true`; when opened standalone (`!window.SpacePointBook`), allow toggling locally for previewing.

```js
const ctx = window.SpacePointBook?.getContext(); // { bookId, userId, canTeacher, lang, theme } | undefined

// Call on spread change (no-op standalone, syncs in LMS)
window.SpacePointBook?.setProgress({ visitedSpreads: ["sp-u1-1"], immediate: true });

// Report exercises with stable exercise_key values across versions
window.SpacePointBook?.reportExercise({
  chapter_key: "u1", exercise_key: "quiz:u1:q1", exercise_type: "quiz",
  prompt_text: "What keeps a satellite in orbit?", answer_json: { selected: "Horizontal velocity" },
  is_correct: true, score_stars: 1, max_stars: 1,
});
window.SpacePointBook?.reportExercise({
  chapter_key: "u1", exercise_key: "nb:u1:reflection", exercise_type: "notebook",
  prompt_text: "Explain altitude vs. speed.", answer_json: { id: "nb-u1-1", text: responseText },
  is_correct: null,
});
window.SpacePointBook?.reportExercise({
  chapter_key: "u1", exercise_key: "lab:u1:orbit-speed", exercise_type: "lab",
  prompt_text: "Orbit Velocity Lab", answer_json: { altitude_km: 550, velocity_kms: 7.59 },
  is_correct: true, score_stars: 3, max_stars: 3,
});
```

### Reader Toolbar Commands (`SP_BOOK_CMD`)

```js
window.addEventListener("message", (event) => {
  const msg = event.data;
  if (!msg || msg.type !== "SP_BOOK_CMD") return;
  const html = document.documentElement;

  if (msg.cmd === "setTheme" && (msg.value === "light" || msg.value === "dark")) {
    html.dataset.theme = msg.value;
  } else if (msg.cmd === "setLang" && (msg.value === "en" || msg.value === "ar")) {
    html.dataset.lang = msg.value;
    html.lang = msg.value;
    html.dir = msg.value === "ar" ? "rtl" : "ltr";
  } else if (msg.cmd === "setTeacher") {
    const allowed = !window.SpacePointBook || window.SpacePointBook.getContext()?.canTeacher === true;
    html.dataset.teacher = allowed && Boolean(msg.value) ? "1" : "0";
  } else if (msg.cmd === "setProfile") {
    applyProfileFilter(String(msg.value || "all"));
  } else if (msg.cmd === "gotoSpread") {
    goToSpreadByName(String(msg.value || ""));
  } else if (msg.cmd === "gotoChapter") {
    goToFirstSpreadOfChapter(String(msg.value || ""));
  } else if (msg.cmd === "prev" || msg.cmd === "next") {
    stepSpread(msg.cmd === "next" ? 1 : -1);
  }
});
```

*(If you also expose `window.viewOfSpread(name)` and `window.go(index)` or `#prev` / `#next` + `#pn`, the LMS bridge hooks navigation automatically.)*

---

## 5. Design System & Layout Rules

- **Palette & radii:** Flat colors only (no gradients): `#18181B` dark cover/surface, `#7C3AED` purple accent, `#FFFFFF` / `#F4F4F5` light surfaces (`#09090B` / `#18181B` / `#27272A` dark), `#16A34A` correct / `#E11D48` error, `border-radius: 10px`.
- **Responsive (`900px`):** Side-by-side 2-column `.side-a` / `.side-b` above `900px`; vertically stacked single scroll below `900px` with sticky `.pager`.
- **Equations (`.eq`):** Never use fixed height or `overflow: hidden` (`height: auto; overflow-wrap: anywhere`).
- **Avoid:** Bloom/5C/Hat chips (`.btab`, `.bbadge`, `.cchip`, `.hatrow`, `.tags`, `.ladder`), emoji icons (use inline SVGs), color-key spreads (`data-name="key"`), or hardcoded `"SPACE."` branding.

---

## 6. Checklist

1. Works standalone when opening `index.html` directly in a browser.
2. `index.html` and `book.json` sit at the `.zip` root (or inside one wrapper folder), using relative paths only (`< 150 MB`, `< 1000` files, no `__sp_runtime__/`).
3. All `outline[].lessons[].spread` and `outline[].key` match `.spread[data-name]` and `[data-ch]`.
4. Cover has `data-book-cover`, renders without JS at `480×640`, and has no cover CTA buttons.
5. Light/dark mode, EN/AR (`rtl`), teacher lock, and mobile stacking (`<= 900px`) all work cleanly.
6. Every quiz/lab/notebook uses `[data-nb]` or `window.SpacePointBook?.reportExercise(...)` with stable keys.
