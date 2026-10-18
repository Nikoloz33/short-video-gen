/**
 * npm run gallery -w video [-- --lang en|ka] [--update | --check]
 *
 * Renders every template's gallery scene (both languages) as a PNG at its "settled" frame into
 * out/gallery/<lang>/ + a contact sheet per language, for visual QA.
 *
 * Snapshot tests: --check compares a 27x48 grayscale thumbnail of each still against
 * video/snapshots/<id>.json (mean absolute difference, tolerant to font anti-aliasing differences
 * between machines) and exits 1 on a mismatch; --update rewrites the baselines.
 */
import fs from 'node:fs';
import path from 'node:path';
import { openBrowser, renderStill, selectComposition } from '@remotion/renderer';
import { GALLERY, TEMPLATES, galleryId } from '../src/examples/gallery';
import type { Lang, Template } from '../src/spec/types';
import { argValue, bundleProject, VIDEO_ROOT } from './lib/bundle';
import { contactSheet, FFMPEG, runOk } from './lib/ffmpeg';
import { FPS } from '../src/lib/time';

const THUMB_W = 27;
const THUMB_H = 48;
/** Mean absolute difference (0-255) above which a still counts as changed. */
export const SNAPSHOT_TOLERANCE = 6;

/** Frame to capture: after all entrances; quiz questions mid-countdown. */
export const settledFrame = (template: Template, durationS: number): number => {
  const t = template === 'quiz_question' ? durationS - 1.5 : Math.min(durationS - 0.4, durationS * 0.8);
  return Math.max(0, Math.round(t * FPS));
};

const thumbnail = async (png: string): Promise<Buffer> => {
  const r = await runOk(FFMPEG, [
    '-hide_banner',
    '-v',
    'error',
    '-i',
    png,
    '-vf',
    `scale=${THUMB_W}:${THUMB_H}:flags=area,format=gray`,
    '-f',
    'rawvideo',
    'pipe:1',
  ]);
  return Buffer.from(r.stdout, 'latin1');
};

export const meanAbsDiff = (a: Uint8Array, b: Uint8Array): number => {
  if (a.length !== b.length) return 255;
  let sum = 0;
  for (let i = 0; i < a.length; i++) sum += Math.abs((a[i] ?? 0) - (b[i] ?? 0));
  return sum / a.length;
};

const main = async () => {
  const update = process.argv.includes('--update');
  const check = process.argv.includes('--check');
  const only = argValue('--lang') as Lang | undefined;
  const langs = (Object.keys(GALLERY) as Lang[]).filter((l) => !only || l === only);
  const snapDir = path.join(VIDEO_ROOT, 'snapshots');
  fs.mkdirSync(snapDir, { recursive: true });

  const serveUrl = await bundleProject();
  const browser = await openBrowser('chrome');
  const failures: string[] = [];
  for (const lang of langs) {
    const dir = path.join(VIDEO_ROOT, '..', 'out', 'gallery', lang);
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    for (const [i, t] of TEMPLATES.entries()) {
      const id = galleryId(t, lang);
      const composition = await selectComposition({ serveUrl, id, puppeteerInstance: browser });
      const frame = settledFrame(t, GALLERY[lang][t].duration_s);
      const out = path.join(dir, `${String(i + 1).padStart(2, '0')}.png`);
      await renderStill({
        composition,
        serveUrl,
        frame,
        output: out,
        scale: 0.5,
        puppeteerInstance: browser,
        imageFormat: 'png',
      });
      if (update || check) {
        const thumb = await thumbnail(out);
        const file = path.join(snapDir, `${id}.json`);
        if (update) {
          fs.writeFileSync(
            file,
            JSON.stringify({ w: THUMB_W, h: THUMB_H, frame, data: thumb.toString('base64') }) + '\n',
          );
        } else {
          const base = fs.existsSync(file)
            ? (JSON.parse(fs.readFileSync(file, 'utf8')) as { data: string })
            : null;
          const diff = base ? meanAbsDiff(thumb, Buffer.from(base.data, 'base64')) : 255;
          const ok = diff <= SNAPSHOT_TOLERANCE;
          if (!ok) failures.push(`${id} (diff ${diff.toFixed(2)})`);
          console.log(`  ${ok ? '✓' : '✗'} ${id}  diff ${diff.toFixed(2)}`);
          continue;
        }
      }
      console.log(`  ${id}  frame ${frame} -> ${path.basename(out)}`);
    }
    await contactSheet(dir, TEMPLATES.length, path.join(dir, '..', `contact-${lang}.png`), 4);
  }
  await browser.close({ silent: true });
  if (failures.length) {
    console.error(
      `✗ ${failures.length} snapshot(s) changed: ${failures.join(', ')}\n  (npm run gallery -w video -- --update if intended)`,
    );
    process.exit(1);
  }
  console.log(update ? '✓ snapshots updated' : check ? '✓ snapshots match' : '✓ gallery rendered');
};

if (process.argv[1] && path.resolve(process.argv[1]).endsWith('gallery.ts')) await main();
