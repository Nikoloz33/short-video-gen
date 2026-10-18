/**
 * npm run fonts -w video
 *
 * 1. Copies the Noto Sans (latin, latin-ext) and Noto Sans Georgian (georgian) woff2 subsets from
 *    @fontsource into public/fonts/ (+ the OFL licence) — fonts are bundled, never loaded from a CDN.
 * 2. Writes src/catalog/fonts.json (the @font-face list with unicode ranges) and
 *    src/catalog/font-metrics.json: per weight, the advance width (em) of every code point the
 *    browser will draw from these faces. textFit.ts measures text with this table, so the agent's
 *    layout check and the templates agree without a browser.
 */
import fs from 'node:fs';
import path from 'node:path';
import * as fontkit from 'fontkit';
import { VIDEO_ROOT } from './lib/bundle';

type Face = { family: string; pkg: string; subset: string; weight: number };

const WEIGHTS = [400, 700];
const FACES: Face[] = WEIGHTS.flatMap((weight) => [
  { family: 'Noto Sans', pkg: 'noto-sans', subset: 'latin', weight },
  { family: 'Noto Sans', pkg: 'noto-sans', subset: 'latin-ext', weight },
  { family: 'Noto Sans Georgian', pkg: 'noto-sans-georgian', subset: 'georgian', weight },
]);

const NODE_MODULES = path.join(VIDEO_ROOT, '..', 'node_modules', '@fontsource');
const PUBLIC_FONTS = path.join(VIDEO_ROOT, 'public', 'fonts');
const CATALOG = path.join(VIDEO_ROOT, 'src', 'catalog');

/** Parses "U+0000-00FF, U+0131, ..." into inclusive [lo, hi] pairs. */
export const parseUnicodeRange = (range: string): [number, number][] =>
  range.split(',').map((part) => {
    const [lo, hi] = part.trim().replace(/^U\+/i, '').split('-');
    const a = parseInt(lo ?? '0', 16);
    return [a, hi ? parseInt(hi, 16) : a];
  });

const unicodeRangeOf = (face: Face): string => {
  const css = fs.readFileSync(path.join(NODE_MODULES, face.pkg, `${face.weight}.css`), 'utf8');
  const block = css
    .split('@font-face')
    .find((b) => b.includes(`-${face.subset}-${face.weight}-normal.woff2`));
  const m = block && /unicode-range:\s*([^;]+);/.exec(block);
  if (!m?.[1]) throw new Error(`no unicode-range for ${face.pkg} ${face.subset} ${face.weight}`);
  return m[1].trim();
};

const main = () => {
  fs.mkdirSync(PUBLIC_FONTS, { recursive: true });
  fs.mkdirSync(CATALOG, { recursive: true });
  const manifest: { family: string; file: string; weight: number; unicodeRange: string }[] = [];
  const metrics: Record<string, Record<string, number>> = {};

  for (const face of FACES) {
    const file = `${face.pkg}-${face.subset}-${face.weight}-normal.woff2`;
    const src = path.join(NODE_MODULES, face.pkg, 'files', file);
    fs.copyFileSync(src, path.join(PUBLIC_FONTS, file));
    const unicodeRange = unicodeRangeOf(face);
    manifest.push({ family: face.family, file, weight: face.weight, unicodeRange });

    const ranges = parseUnicodeRange(unicodeRange);
    const font = fontkit.openSync(src) as fontkit.Font;
    const table = (metrics[String(face.weight)] ??= {});
    for (const cp of font.characterSet) {
      if (!ranges.some(([lo, hi]) => cp >= lo && cp <= hi)) continue;
      const ch = String.fromCodePoint(cp);
      // Earlier faces win, like the CSS font stack ('Noto Sans' before 'Noto Sans Georgian').
      if (table[ch] !== undefined) continue;
      table[ch] = Math.round((font.glyphForCodePoint(cp).advanceWidth / font.unitsPerEm) * 10000) / 10000;
    }
  }

  const licence = path.join(NODE_MODULES, 'noto-sans', 'LICENSE');
  fs.copyFileSync(licence, path.join(PUBLIC_FONTS, 'OFL.txt'));
  fs.writeFileSync(path.join(CATALOG, 'fonts.json'), JSON.stringify(manifest, null, 2) + '\n');
  fs.writeFileSync(
    path.join(CATALOG, 'font-metrics.json'),
    JSON.stringify({ version: 1, weights: metrics }) + '\n',
  );
  for (const [w, t] of Object.entries(metrics))
    console.log(`  weight ${w}: ${Object.keys(t).length} code points`);
  console.log(`✓ ${manifest.length} faces -> ${PUBLIC_FONTS}`);
};

if (process.argv[1] && path.resolve(process.argv[1]).endsWith('gen-fonts.ts')) main();
