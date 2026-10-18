/**
 * npm run still -w video -- <compositionId> [--frame N] [--scale 0.5] [--props file.json] [--out file.png]
 * Renders one PNG for visual QA (default out/stills/<id>.png).
 */
import fs from 'node:fs';
import path from 'node:path';
import { renderStill, selectComposition } from '@remotion/renderer';
import { argValue, bundleProject, VIDEO_ROOT } from './lib/bundle';

const id = process.argv[2];
if (!id || id.startsWith('--')) {
  console.error('usage: npm run still -w video -- <compositionId> [--frame N] [--scale S] [--props f.json]');
  process.exit(2);
}
const frame = Number(argValue('--frame') ?? 0);
const scale = Number(argValue('--scale') ?? 0.5);
const propsFile = argValue('--props');
const inputProps = propsFile
  ? (JSON.parse(fs.readFileSync(propsFile, 'utf8')) as Record<string, unknown>)
  : {};
const out = argValue('--out') ?? path.join(VIDEO_ROOT, '..', 'out', 'stills', `${id}.png`);
fs.mkdirSync(path.dirname(out), { recursive: true });

const serveUrl = await bundleProject();
const composition = await selectComposition({ serveUrl, id, inputProps });
await renderStill({ composition, serveUrl, frame, output: out, scale, inputProps, imageFormat: 'png' });
console.log(`✓ ${out}`);
