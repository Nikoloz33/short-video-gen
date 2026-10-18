/**
 * npm run render:smoke — bundle + render the placeholder at quarter size and check it with ffprobe.
 * Proves the Remotion toolchain, Chromium download and system ffmpeg all work on this machine.
 */
import fs from 'node:fs';
import path from 'node:path';
import { renderMedia, selectComposition } from '@remotion/renderer';
import { bundleProject, fmtBytes, VIDEO_ROOT } from './lib/bundle';
import { probe } from './lib/ffmpeg';

const out = path.join(VIDEO_ROOT, '..', 'out', 'smoke', 'placeholder.mp4');
fs.mkdirSync(path.dirname(out), { recursive: true });

const t0 = Date.now();
const serveUrl = await bundleProject();
const composition = await selectComposition({ serveUrl, id: 'Placeholder' });
await renderMedia({
  composition,
  serveUrl,
  codec: 'h264',
  outputLocation: out,
  overwrite: true,
  scale: 0.25,
  imageFormat: 'jpeg',
  licenseKey: process.env.REMOTION_LICENSE_KEY || null,
});
const info = await probe(out);
const ok =
  info.vcodec === 'h264' && info.width === 270 && info.height === 480 && Math.abs(info.fps - 30) < 0.01;
console.log(
  `${ok ? '✓' : '✗'} ${out}  ${info.width}x${info.height} @ ${info.fps} fps, ${info.duration.toFixed(2)} s, ` +
    `${fmtBytes(info.size)}, ${((Date.now() - t0) / 1000).toFixed(1)} s wall`,
);
process.exit(ok ? 0 : 1);
