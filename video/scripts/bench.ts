/**
 * npm run bench -w video [-- --lang en|ka] [--preset preview|final|both]
 * Renders the template reel (~57 s) through the render worker and prints the speed numbers that the
 * UI shows: wall time, render fps, realtime factor and per-stage timings.
 */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { galleryReel } from '../src/examples/gallery';
import type { Lang } from '../src/spec/types';
import { argValue, VIDEO_ROOT } from './lib/bundle';

const lang = (argValue('--lang') ?? 'en') as Lang;
const which = argValue('--preset') ?? 'both';
const presets = which === 'both' ? ['preview', 'final'] : [which];
const spec = galleryReel(lang);
const total = spec.scenes.reduce((n, s) => n + s.duration_s, 0);
// Spawn node + tsx's CLI directly: no shell, so paths with spaces are safe.
const tsxCli = path.join(VIDEO_ROOT, '..', 'node_modules', 'tsx', 'dist', 'cli.mjs');

let failed = false;
for (const preset of presets) {
  const out_dir = path.join(VIDEO_ROOT, '..', 'out', 'bench', preset);
  const r = spawnSync(process.execPath, [tsxCli, path.join(VIDEO_ROOT, 'scripts', 'render-worker.ts')], {
    input: JSON.stringify({ cmd: 'render', spec, preset, out_dir }),
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  });
  const lines = r.stdout.trim().split('\n').filter(Boolean);
  const last = JSON.parse(lines.at(-1) ?? '{}') as {
    type?: string;
    durationMs?: number;
    totalFrames?: number;
    stages?: Record<string, number>;
    checks?: { name: string; ok: boolean }[];
    message?: string;
  };
  if (last.type !== 'done') {
    console.error(`✗ ${preset}: ${last.message ?? r.stderr.slice(-800)}`);
    failed = true;
    continue;
  }
  const wall = (last.durationMs ?? 0) / 1000;
  const fps = (last.totalFrames ?? 0) / ((last.stages?.render_ms ?? 1) / 1000);
  console.log(
    `${preset.padEnd(8)} ${total.toFixed(1)} s video, ${last.totalFrames} frames: wall ${wall.toFixed(1)} s, ` +
      `render ${fps.toFixed(0)} fps, realtime x${(total / wall).toFixed(2)}, stages ${JSON.stringify(last.stages)}, ` +
      `checks ${last.checks?.every((c) => c.ok) ? 'ok' : 'FAILED'}`,
  );
}
process.exit(failed ? 1 : 0);
