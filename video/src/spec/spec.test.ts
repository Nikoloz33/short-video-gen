import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { VideoSpecSchema } from '../generated/spec.zod';
import { checkSpec } from '../lib/checkSpec';
import { galleryReel, gallerySpec, TEMPLATES } from '../examples/gallery';

const FIXTURES = path.resolve(__dirname, '..', '..', '..', 'data', 'fixtures', 'specs');
const load = (name: string): unknown => JSON.parse(fs.readFileSync(path.join(FIXTURES, name), 'utf8'));

type Case = { name: string; path: (string | number)[]; value?: unknown; delete?: boolean };
const patch = (doc: unknown, c: Case): unknown => {
  const copy = structuredClone(doc) as Record<string | number, unknown>;
  let node = copy;
  for (const p of c.path.slice(0, -1)) node = node[p] as Record<string | number, unknown>;
  const last = c.path.at(-1)!;
  if (c.delete) delete node[last];
  else node[last] = c.value;
  return copy;
};

describe('generated zod schema', () => {
  it('accepts the hand-written fixture and it passes the layout check', () => {
    const spec = VideoSpecSchema.parse(load('handwash-en.json'));
    expect(spec.scenes).toHaveLength(10);
    expect(checkSpec(spec)).toEqual([]);
  });

  it('accepts every gallery spec (generated types and templates agree)', () => {
    for (const lang of ['en', 'ka'] as const) {
      expect(() => VideoSpecSchema.parse(galleryReel(lang))).not.toThrow();
      for (const t of TEMPLATES) expect(() => VideoSpecSchema.parse(gallerySpec(lang, t))).not.toThrow();
    }
  });

  const { cases } = load('invalid.json') as { cases: Case[] };
  it.each(cases.map((c) => [c.name, c] as const))('rejects: %s', (_name, c) => {
    expect(VideoSpecSchema.safeParse(patch(load('handwash-en.json'), c)).success).toBe(false);
  });
});
