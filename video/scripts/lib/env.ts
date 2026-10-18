/**
 * Minimal .env loader: finds the repo-root .env by walking up from the cwd, so scripts work from
 * both the repo root and the `video/` workspace. Existing environment variables win.
 */
import fs from 'node:fs';
import path from 'node:path';

export const findUp = (name: string, from = process.cwd()): string | undefined => {
  let dir = path.resolve(from);
  for (;;) {
    const candidate = path.join(dir, name);
    if (fs.existsSync(candidate)) return candidate;
    const parent = path.dirname(dir);
    if (parent === dir) return undefined;
    dir = parent;
  }
};

/** Parses KEY=value lines; strips matching single/double quotes around the value. */
export const parseEnv = (text: string): Record<string, string> => {
  const out: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const m = /^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/.exec(line);
    if (!m || !m[1] || line.trimStart().startsWith('#')) continue;
    let value = m[2] ?? '';
    if (value.length >= 2 && (value[0] === '"' || value[0] === "'") && value.endsWith(value[0])) {
      value = value.slice(1, -1);
    }
    out[m[1]] = value;
  }
  return out;
};

export const loadEnv = (): void => {
  const file = findUp('.env');
  if (!file) return;
  for (const [k, v] of Object.entries(parseEnv(fs.readFileSync(file, 'utf8')))) {
    if (v && process.env[k] === undefined) process.env[k] = v;
  }
};
