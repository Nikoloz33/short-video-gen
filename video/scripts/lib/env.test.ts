import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { findUp, parseEnv } from './env';

describe('env', () => {
  it('parses values, strips quotes, skips comments', () => {
    const env = parseEnv('# c\nA=1\nB="two words"\nC=\'x\'\nD=C:\\ffmpeg\\bin\n  E = spaced  \nnot a line');
    expect(env).toEqual({ A: '1', B: 'two words', C: 'x', D: 'C:\\ffmpeg\\bin', E: 'spaced' });
  });

  it('finds a file in a parent directory', () => {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'env-'));
    const deep = path.join(root, 'a', 'b');
    fs.mkdirSync(deep, { recursive: true });
    fs.writeFileSync(path.join(root, '.marker-env'), 'X=1');
    expect(findUp('.marker-env', deep)).toBe(path.join(root, '.marker-env'));
    expect(findUp('.definitely-missing-file', deep)).toBeUndefined();
  });
});
