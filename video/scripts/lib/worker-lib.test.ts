import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { galleryReel, galleryScene } from '../../src/examples/gallery';
import type { Scene } from '../../src/spec/types';
import {
  defaultConcurrency,
  hashTree,
  parseRequest,
  PRESETS,
  quizJson,
  RequestError,
  rewriteAudio,
  safeMediaPath,
  throttle,
} from './worker-lib';

describe('parseRequest', () => {
  it('parses check and render requests', () => {
    expect(parseRequest('{"cmd":"check","spec":{}}')).toEqual({ cmd: 'check', spec: {} });
    const r = parseRequest(
      '{"cmd":"render","spec":{},"preset":"final","out_dir":"o","concurrency":4,"name":"v2"}',
    );
    expect(r).toMatchObject({ cmd: 'render', preset: 'final', out_dir: 'o', concurrency: 4, name: 'v2' });
  });

  it.each([
    ['not json', 'request is not valid JSON'],
    ['[1]', 'unknown cmd'],
    ['{"cmd":"render","preset":"x","out_dir":"o"}', 'preset'],
    ['{"cmd":"render","preset":"final"}', 'out_dir'],
    ['{"cmd":"render","preset":"final","out_dir":"o","concurrency":0}', 'concurrency'],
    ['{"cmd":"render","preset":"final","out_dir":"o","name":"../x"}', 'name'],
  ])('rejects %s', (text, msg) => {
    expect(() => parseRequest(text)).toThrow(RequestError);
    expect(() => parseRequest(text)).toThrow(msg);
  });
});

describe('media', () => {
  it('rewrites relative audio paths to the media server and keeps URLs', () => {
    const a: Scene = {
      ...galleryScene('en', 'title_card'),
      audio: { src: 'audio/s 1.wav', duration_s: 2, start_s: 0.3 },
    };
    const b: Scene = {
      ...galleryScene('en', 'step_card'),
      audio: { src: 'http://x/y.wav', duration_s: 2, start_s: 0.3 },
    };
    const out = rewriteAudio({ ...galleryReel('en'), scenes: [a, b] }, 'http://127.0.0.1:9');
    expect(out.scenes[0]!.audio!.src).toBe('http://127.0.0.1:9/audio/s%201.wav');
    expect(out.scenes[1]!.audio!.src).toBe('http://x/y.wav');
  });

  it('keeps media requests inside the root', () => {
    const root = path.resolve('media-root');
    expect(safeMediaPath(root, '/audio/a.wav')).toBe(path.join(root, 'audio', 'a.wav'));
    expect(safeMediaPath(root, '/../secret.txt')).toBeNull();
    expect(safeMediaPath(root, '/%2e%2e/secret.txt')).toBeNull();
    expect(safeMediaPath(root, '/')).toBeNull();
    expect(safeMediaPath(root, '/%E0%A4%A')).toBeNull();
  });
});

describe('quizJson', () => {
  it('lists questions with start time and the explanation of the following answer', () => {
    const spec = galleryReel('en');
    const q = quizJson(spec);
    expect(q.questions).toHaveLength(1);
    const idx = spec.scenes.findIndex((s) => s.template === 'quiz_question');
    const at = spec.scenes.slice(0, idx).reduce((n, s) => n + s.duration_s, 0);
    expect(q.questions[0]).toMatchObject({
      at_s: at,
      correct_index: 1,
      explanation: expect.stringContaining('20'),
    });
  });
});

describe('misc', () => {
  it('hashTree changes when a file changes', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'hash-'));
    fs.writeFileSync(path.join(dir, 'a.txt'), '1');
    const h1 = hashTree([dir]);
    expect(hashTree([dir])).toBe(h1);
    fs.writeFileSync(path.join(dir, 'a.txt'), '2');
    expect(hashTree([dir])).not.toBe(h1);
    expect(hashTree([dir], 'x')).not.toBe(hashTree([dir]));
  });

  it('throttle lets one event through per window, plus forced ones', () => {
    const t = throttle(100);
    expect([t(0), t(50), t(100), t(120, true), t(150)]).toEqual([true, false, true, true, false]);
  });

  it('presets and concurrency', () => {
    expect(PRESETS.final).toMatchObject({ width: 1080, height: 1920, fps: 30 });
    expect(PRESETS.preview.width * 2).toBe(PRESETS.final.width);
    expect(defaultConcurrency(16)).toBe(8);
    expect(defaultConcurrency(1)).toBe(1);
  });
});
