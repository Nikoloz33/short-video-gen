// Copies the bundled Noto woff2 files from the video project so the UI uses the same local fonts.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const src = path.join(here, '..', '..', 'video', 'public', 'fonts');
const dst = path.join(here, '..', 'public', 'fonts');
fs.mkdirSync(dst, { recursive: true });
for (const f of fs.readdirSync(src)) {
  if (f.endsWith('.woff2') || f === 'OFL.txt') fs.copyFileSync(path.join(src, f), path.join(dst, f));
}
