import sharp from 'sharp';
import { readFile, writeFile, stat } from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const base = path.join(__dirname, '..', 'public', 'assets', 'satkit');
const manifestPath = path.join(base, 'manifest.json');

const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));

let before = 0;
let after = 0;
let converted = 0;

for (const f of manifest.seq) {
  const srcRel = f.src;
  const srcPath = path.join(base, srcRel);
  const outRel = srcRel.replace(/\.png$/i, '.webp');
  const outPath = path.join(base, outRel);

  const { size: srcSize } = await stat(srcPath);
  await sharp(srcPath)
    .webp({ quality: 90, alphaQuality: 100, nearLossless: false, effort: 6 })
    .toFile(outPath);
  const { size: outSize } = await stat(outPath);

  before += srcSize;
  after += outSize;
  converted++;
  f.src = outRel;
}

await writeFile(manifestPath, JSON.stringify(manifest));

console.log(`Converted ${converted} frames`);
console.log(`Before: ${(before / 1024 / 1024).toFixed(1)} MB`);
console.log(`After:  ${(after / 1024 / 1024).toFixed(1)} MB`);
console.log(`Saved:  ${(100 * (1 - after / before)).toFixed(0)}%`);
