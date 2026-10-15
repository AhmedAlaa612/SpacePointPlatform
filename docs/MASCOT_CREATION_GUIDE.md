# Mascot Creation Guide & Agent Handoff

This document is a comprehensive, step-by-step guide for any AI agent or developer to create, build, verify, and register new cursor-tracking mascots for SpacePoint using the `page-mascot` pipeline.

---

## 1. Overview & Architecture

Each mascot consists of **exactly two $3\times3$ WebP sprite sheets**:
1. **`directions.webp`**: 9 head angles that rotate to watch the user's mouse pointer across the screen.
2. **`reactions.webp`**: 9 facial expressions triggered on click / poke ("boop").

The component swaps between them purely by shifting CSS `background-position` on a `300% 300%` container. There is **no per-frame JavaScript and no external animation library**.

```
3x3 Grid Layout (0-indexed):
Row 0:  [0] up-left    | [1] up        | [2] up-right
Row 1:  [3] left       | [4] center    | [5] right
Row 2:  [6] down-left  | [7] down      | [8] down-right
```

---

## 2. Directory Structure

```text
spacepoint/
├── .agents/skills/page-mascot/scripts/
│   ├── build.py           # Aligns, scales, softens bottom edge, and generates .webp
│   ├── verify.py          # Checks drift, shift, overlap, and palette stability
│   └── mascot.py          # Pipeline orchestration script
├── characters/
│   └── <character-name>/
│       ├── directions.png # 1024x1024 transparent RGBA source
│       └── reactions.png  # 1024x1024 transparent RGBA source
├── frontend/
│   ├── public/
│   │   ├── mascots/       # Compiled production .webp files
│   │   │   ├── <name>-directions.webp
│   │   │   └── <name>-reactions.webp
│   │   └── mascots.html   # Standalone Mascot Showcase & Playground
│   └── src/
│       └── components/
│           └── Mascot.tsx # Reusable zero-dependency React component
└── docs/
    └── MASCOT_CREATION_GUIDE.md
```

---

## 3. Step-by-Step Creation Pipeline

### Step 1: Generate Sheet 1 (Directions)

Using an image generator (DALL-E 3, Midjourney, Flux, or Antigravity's `image-generator` subagent), create the **Directions Sheet**.

**Prompt Template:**
```text
Generate a 3x3 grid sprite sheet of {DESCRIBE_CHARACTER}. Cute storybook sticker art: clean bold black outlines with some weight variation, big expressive eyes each with a bright white catchlight, soft pink cheek blush, and warm saturated colours. Charming and playful, full of small appealing details. Not flat, not plain, not minimal. No photorealism, no heavy 3D gloss, no airbrushed gradients.

This sheet is NINE HEAD DIRECTIONS, not expressions -- the face keeps the same calm expression in every cell and only the direction the head is TURNED changes.

LAYOUT: 3 columns by 3 rows, evenly spaced, solid white background. Each drawing is head plus upper shoulders, centred in its cell, same character and same head size in all nine cells.

FRAMING: a PORTRAIT BUST. Head, neck and shoulders only. NO arms, NO hands, NO legs, NO lower body. The shoulders are the lowest thing in the cell.

PROPORTIONS: a BIG HEAD chibi that still has a real body. The head is large and dominant, and the shoulders are roughly TWO THIRDS the width of the head.

THE RULE THAT MATTERS MOST: draw the BODY ONCE and reuse it. The neck, chest and shoulders must be the EXACT SAME SHAPE in the EXACT SAME POSITION in all nine cells. The body always faces the viewer. Only the head rotates, on top of an unchanging body.

MARGINS: each character must sit ENTIRELY INSIDE its own cell with a wide empty gap on all four sides. Draw it at roughly 75% of the cell height, centred, leaving clear empty space above the head AND below the shoulders. Nothing may touch or cross a cell boundary.

Turn the whole head clearly:
Row 1: up-left, up, up-right.
Row 2: left, straight at the viewer, right.
Row 3: down-left, down, down-right.

NO hearts, NO sparkles, NO "zzz", NO spiral eyes -- no floating symbols.
Square image, 1024x1024.
```

---

### Step 2: Generate Sheet 2 (Reactions / Expressions)

Pass the directions sheet as visual reference so the character remains identical.

**Prompt Template:**
```text
The attached image is a 3x3 head-direction sprite sheet. Produce the MATCHING EXPRESSIONS sheet for that same character: {DESCRIBE_CHARACTER}. Copy the character from the attached image exactly: the same colours, markings, fur/skin tone, line weight, and clothing.

NOT head directions. The character faces STRAIGHT AT THE VIEWER in all nine cells, head perfectly straight. The only thing that changes between cells is the FACE, plus subtle floating reaction symbols:

Row 1:
- Cell 1 (blink): Eyes gently closed in a happy arc (^_^), sweet smile.
- Cell 2 (heart): Big overjoyed smile, pink cheek blush, one small red cartoon heart near cheek.
- Cell 3 (sparkle): Wide excited sparkling eyes, happy open mouth, one tiny 4-point gold star sparkle.
Row 2:
- Cell 4 (surprised): Wide round eyes, raised eyebrows, cute small 'o' shaped mouth.
- Cell 5 (wink): Cheerful one-eyed wink, playful confident smile.
- Cell 6 (bashful): Rosy pink cheeks, sweet shy downward smile.
Row 3:
- Cell 7 (sleepy): Drowsy half-lidded eyes, peaceful gentle expression.
- Cell 8 (dizzy): Playful cartoon spiral/swirl eyes, slightly wobbly mouth.
- Cell 9 (delighted): Laughing expression, eyes crinkled in joy, big radiant smile.

CRITICAL: Same art style, same palette, same line weight, same proportions, and EXACTLY THE SAME SIZE AND POSITION IN THE CELL as the attached sheet. The chest and shoulders must be identical. Square 1024x1024 image on a solid white background.
```

---

### Step 3: Transparent Alpha Isolation (Critical!)

> [!CAUTION]
> [!TIP]
> **The Golden Method: Solid Magenta Background (`#FF00FF`) + `key_sheet.py`**
> Characters often wear white (spacesuits, kanduras, ghutras). Generating on a white background risks threshold flood fills eating into the clothing borders, creating dark holes on dark pages.
>
> By prompting for a solid flat magenta background (`#FF00FF`), the key color never collides with character clothes or skin. Run the built-in script:
> ```bash
> python .agents/skills/page-mascot/scripts/key_sheet.py "path/to/raw_directions.jpg" "characters/<name>/directions.png" --size 2048
> python .agents/skills/page-mascot/scripts/key_sheet.py "path/to/raw_reactions.jpg" "characters/<name>/reactions.png" --size 2048
> ```
> This script automatically:
> 1. Detects exact key color drift from borders.
> 2. Applies per-cell boundary connectivity so internal pinks/blush are never keyed out.
> 3. Eliminates purple edge fringing via edge-band despill unmixing.
> 4. Upscales smoothly to 2048x2048 for high-DPI crisp rendering.

---

### Step 4: Compile & Build Atlases

Run the build script from the project root. You can set `MASCOT_TILE=480` for high-resolution sharpness (default is 360).

In PowerShell:
```powershell
$env:MASCOT_DEST = "frontend\public\mascots"
$env:MASCOT_TILE = "480"
python .agents/skills/page-mascot/scripts/build.py <name> --anchor body
```

In Bash:
```bash
MASCOT_DEST="frontend/public/mascots" MASCOT_TILE="480" python3 .agents/skills/page-mascot/scripts/build.py <name> --anchor body
```

---

### Step 5: Verify Alignment & Quality

Run `verify.py` to test whether the character drifts or jumps on click:

```powershell
$env:MASCOT_DEST = "frontend\public\mascots"
python .agents/skills/page-mascot/scripts/verify.py <name>
```

**Passing Criteria:**
* **`worst shift`:** `< 1.50 px` (ideally `0.00 px`). If higher, re-run `build.py` with `--anchor head` or check character margins.
* **`worst width change`:** `< 5.0%`.
* **`overlap`:** `> 65%`.

---

## 4. Registering the Mascot

### In the HTML Showcase (`frontend/public/mascots.html`)
Open `frontend/public/mascots.html` and add your new character to the `MASCOTS` array:

```javascript
const MASCOTS = [
  {
    id: "emirati-kid",
    name: "Emirati Space Cadet",
    role: "SpacePoint Student Explorer",
    directions: "/mascots/emirati-kid-directions.webp",
    reactions: "/mascots/emirati-kid-reactions.webp"
  },
  {
    id: "falcon-bot",
    name: "Falcon Rover",
    role: "Mars Exploration Drone",
    directions: "/mascots/falcon-bot-directions.webp",
    reactions: "/mascots/falcon-bot-reactions.webp"
  }
];
```

Test it immediately in your browser at:
👉 `http://localhost:5173/mascots.html`

### In a React Component
```tsx
import { Mascot } from "@/components/Mascot";

export function MyPage() {
  return (
    <Mascot
      directions="/mascots/<name>-directions.webp"
      reactions="/mascots/<name>-reactions.webp"
      size={140}
      label="SpacePoint Mascot"
    />
  );
}
```
*(Props: `directions` [string], `reactions` [string], `size?` [number, default 140], `className?` [string], `label?` [string]).*
