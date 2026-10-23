/**
 * Smoke test of the BUILT UI against the API in fake mode (no model costs, fake renderer).
 *   npm run build -w web && npm run e2e -w web
 * Reuses Remotion's Chrome headless shell when present, so no extra browser download is needed.
 */
import { defineConfig } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

const root = path.resolve(here, '..');
const shell = path.join(
  root,
  'node_modules',
  '.remotion',
  'chrome-headless-shell',
  process.platform === 'win32' ? 'win64' : 'linux64',
  process.platform === 'win32' ? 'chrome-headless-shell-win64' : 'chrome-headless-shell-linux64',
  process.platform === 'win32' ? 'chrome-headless-shell.exe' : 'chrome-headless-shell',
);
const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'instructvid-e2e-'));
const uv = process.env.UV_BIN ?? 'uv';

export default defineConfig({
  testDir: 'e2e',
  timeout: 120_000,
  use: {
    baseURL: 'http://127.0.0.1:8765',
    launchOptions: fs.existsSync(shell) ? { executablePath: shell } : {},
  },
  webServer: {
    command: `"${uv}" run uvicorn agent.api.app:app --host 127.0.0.1 --port 8765`,
    cwd: root,
    url: 'http://127.0.0.1:8765/api/health',
    reuseExistingServer: false,
    timeout: 120_000,
    env: { APP_FAKE: '1', APP_TOKEN: 'e2e', DATA_DIR: dataDir, UV_PYTHON_PREFERENCE: 'only-managed' },
  },
});
