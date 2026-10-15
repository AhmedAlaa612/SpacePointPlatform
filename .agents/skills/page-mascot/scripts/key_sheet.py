"""Key a 3x3 sprite sheet drawn on a flat magenta (#FF00FF) background into a clean RGBA PNG.

Why magenta and not white: characters wear white (space suit, kandura, ghutra). A white-threshold
flood fill eats into those areas wherever they touch the background, punching holes that show the
page (dark) through -- the "black areas". A saturated key colour never appears on the character.

Steps:
  1. Estimate the actual key colour from the image border (generators drift off pure #FF00FF).
  2. Soft alpha from colour distance to the key (two thresholds -> smooth antialiased edge).
  3. Keep only regions connected to each cell's border as background (so any stray key-ish
     pixel inside the character is never removed), done per cell.
  4. Despill: remove the magenta tint from semi-transparent edge pixels.
  5. Optional upscale (Lanczos) so the build step has more pixels to work with.

    python key_sheet.py <in> <out.png> [--size 2048]
"""
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

src, dst = sys.argv[1], sys.argv[2]
size = int(sys.argv[sys.argv.index('--size') + 1]) if '--size' in sys.argv else None

im = Image.open(src).convert('RGB')
if size and im.size[0] != size:
    im = im.resize((size, size), Image.LANCZOS)
rgb = np.asarray(im).astype(np.float32)
H, W, _ = rgb.shape

# 1. key colour from a thin border strip
border = np.concatenate([rgb[:4].reshape(-1, 3), rgb[-4:].reshape(-1, 3),
                         rgb[:, :4].reshape(-1, 3), rgb[:, -4:].reshape(-1, 3)])
key = np.median(border, axis=0)
print('key colour', key.round())

# 2. distance-based soft alpha. "Magenta-ness" = min(R,B) - G is robust to brightness drift.
mag = np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1]
key_mag = min(key[0], key[2]) - key[1]
dist = np.linalg.norm(rgb - key, axis=2)
LO, HI = 60.0, 140.0                     # dist below LO = background, above HI = character
alpha = np.clip((dist - LO) / (HI - LO), 0, 1)
alpha = np.where(mag > key_mag * 0.55, np.minimum(alpha, 1 - np.clip((mag - key_mag * 0.55) / (key_mag * 0.35), 0, 1)), alpha)

# 3. background must be connected to the cell border (per cell)
bgmask = alpha < 0.5
keep_bg = np.zeros_like(bgmask)
ch, cw = H // 3, W // 3
for r in range(3):
    for c in range(3):
        y0, y1 = r * ch, (r + 1) * ch if r < 2 else H
        x0, x1 = c * cw, (c + 1) * cw if c < 2 else W
        cell = bgmask[y0:y1, x0:x1]
        lab, n = ndimage.label(cell)
        edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        keep_bg[y0:y1, x0:x1] = np.isin(lab, edge[edge > 0])
# grow a band around kept background: only pixels in this band may be partially transparent,
# so nothing inside the character (blush, hearts) is ever touched.
band = ndimage.binary_dilation(keep_bg, iterations=8) & ~keep_bg
# In the band, a pixel is (a * character + (1 - a) * key). The magenta EXCESS min(R,B) - G is
# ~key_mag for pure key and ~0 for the dark outline / skin / white, so it estimates (1 - a).
excess_frac = np.clip((mag - 8) / (key_mag - 8), 0, 1)
band_alpha = np.minimum(alpha, 1 - excess_frac)
alpha = np.where(band, band_alpha, np.where(keep_bg, 0.0, 1.0))
alpha[keep_bg] = 0
# drop specks
alpha[alpha < 0.06] = 0

# 4. unmix the key colour out of partially transparent pixels
a = alpha[..., None]
safe = np.maximum(a, 1e-3)
unmixed = (rgb - (1 - a) * key) / safe
out_rgb = np.where((a > 0) & (a < 0.999), np.clip(unmixed, 0, 255), rgb)
# 5. despill anything left in the band: no pixel there may be more magenta than neutral
r_, g_, b_ = out_rgb[..., 0], out_rgb[..., 1], out_rgb[..., 2]
spill = np.clip(np.minimum(r_, b_) - g_, 0, None)
for ch_i in (0, 2):
    out_rgb[..., ch_i] = np.where(band, out_rgb[..., ch_i] - spill, out_rgb[..., ch_i])
out_rgb[alpha == 0] = 0

out = np.dstack([np.clip(out_rgb, 0, 255), alpha * 255]).astype(np.uint8)
Image.fromarray(out, 'RGBA').save(dst)
print(f'saved {dst}  {W}x{H}  transparent {(alpha == 0).mean() * 100:.1f}%')
