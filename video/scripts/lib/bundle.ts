/**
 * Bundle the Remotion project once per process and clean the temp bundle up on exit.
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const VIDEO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

let cached: Promise<string> | undefined;

export const bundleProject = (onProgress?: (pct: number) => void): Promise<string> => {
  cached ??= (async () => {
    const { bundle } = await import('@remotion/bundler');
    const dir = await bundle({
      entryPoint: path.join(VIDEO_ROOT, 'src', 'index.ts'),
      publicDir: path.join(VIDEO_ROOT, 'public'),
      onProgress: (p) => onProgress?.(p),
    });
    // Each bundle copies public/ into the temp folder and Remotion never deletes it: remove ours on
    // exit — only a remotion bundle dir inside the system temp folder.
    const tmp = path.resolve(os.tmpdir());
    const abs = path.resolve(dir);
    if (abs.startsWith(tmp + path.sep) && path.basename(abs).startsWith('remotion-webpack-bundle-')) {
      process.on('exit', () => {
        try {
          fs.rmSync(abs, { recursive: true, force: true });
        } catch {
          /* best effort */
        }
      });
    }
    return dir;
  })();
  return cached;
};

export const argValue = (name: string): string | undefined => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
};

export const fmtBytes = (n: number): string =>
  n > 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(2)} MB` : `${(n / 1024).toFixed(0)} KB`;
