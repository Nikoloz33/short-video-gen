/**
 * Pure helpers of the render worker (protocol, presets, quiz export, bundle hash) — unit tested.
 */
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import type { CheckLimits } from '../../src/lib/checkSpec';
import type { Scene, VideoSpec } from '../../src/spec/types';

export type Preset = {
  width: number;
  height: number;
  fps: number;
  scale: number;
  crf: number;
  jpegQuality: number;
  x264: 'ultrafast' | 'veryfast';
  /** Final renders get a whole-mix loudness pass; previews only remux (clips are pre-normalised). */
  normalizeLoudness: boolean;
};

/** Composition per preset: previews render the same spec at 15 fps (half the frames). */
export const COMPOSITION: Record<'preview' | 'final', string> = {
  preview: 'InstructionVideoPreview',
  final: 'InstructionVideo',
};

/** Default concurrency: above ~8 Chromium tabs Remotion runs short of memory for parallel encoding. */
export const defaultConcurrency = (cpus: number): number => Math.max(1, Math.min(8, cpus - 1));

/** Mirrors config/app.yaml `presets`. */
export const PRESETS: Record<'preview' | 'final', Preset> = {
  preview: {
    width: 540,
    height: 960,
    fps: 15,
    scale: 0.5,
    crf: 28,
    jpegQuality: 70,
    x264: 'ultrafast',
    normalizeLoudness: false,
  },
  final: {
    width: 1080,
    height: 1920,
    fps: 30,
    scale: 1,
    crf: 20,
    jpegQuality: 85,
    x264: 'veryfast',
    normalizeLoudness: true,
  },
};

export type RenderRequest = {
  cmd: 'render';
  spec: unknown;
  preset: 'preview' | 'final';
  out_dir: string;
  /** Local directory that relative audio paths in the spec are resolved against. */
  media_root?: string;
  concurrency?: number;
  timeout_s?: number;
  /** Basename for output files (default "video"). */
  name?: string;
  /** Override duration limits of the layout check (tests render short clips). */
  limits?: Partial<CheckLimits>;
};
export type CheckRequest = { cmd: 'check'; spec: unknown; limits?: Partial<CheckLimits> };
export type WorkerRequest = RenderRequest | CheckRequest;

export class RequestError extends Error {}

const LIMIT_KEYS: readonly string[] = ['minTotalS', 'maxTotalS', 'minSceneS', 'maxSceneS'];

const parseLimits = (v: unknown): Partial<CheckLimits> | undefined => {
  if (v === undefined) return undefined;
  if (!v || typeof v !== 'object') throw new RequestError('limits must be an object');
  const out: Partial<CheckLimits> = {};
  for (const [k, val] of Object.entries(v)) {
    if (!LIMIT_KEYS.includes(k) || typeof val !== 'number') throw new RequestError(`bad limit ${k}`);
    out[k as keyof CheckLimits] = val;
  }
  return out;
};

export const parseRequest = (text: string): WorkerRequest => {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    throw new RequestError('request is not valid JSON');
  }
  if (!raw || typeof raw !== 'object') throw new RequestError('request must be a JSON object');
  const r = raw as Record<string, unknown>;
  const limits = parseLimits(r.limits);
  if (r.cmd === 'check') return { cmd: 'check', spec: r.spec, ...(limits ? { limits } : {}) };
  if (r.cmd !== 'render')
    throw new RequestError(`unknown cmd ${JSON.stringify(r.cmd)} (expected "render" or "check")`);
  if (r.preset !== 'preview' && r.preset !== 'final')
    throw new RequestError('preset must be "preview" or "final"');
  if (typeof r.out_dir !== 'string' || !r.out_dir) throw new RequestError('out_dir is required');
  if (r.concurrency !== undefined && (!Number.isInteger(r.concurrency) || (r.concurrency as number) < 1)) {
    throw new RequestError('concurrency must be a positive integer');
  }
  if (r.name !== undefined && (typeof r.name !== 'string' || !/^[\w-]{1,64}$/.test(r.name))) {
    throw new RequestError('name must match [A-Za-z0-9_-]{1,64}');
  }
  return {
    cmd: 'render',
    spec: r.spec,
    preset: r.preset,
    out_dir: r.out_dir,
    ...(typeof r.media_root === 'string' ? { media_root: r.media_root } : {}),
    ...(typeof r.concurrency === 'number' ? { concurrency: r.concurrency } : {}),
    ...(typeof r.timeout_s === 'number' ? { timeout_s: r.timeout_s } : {}),
    ...(typeof r.name === 'string' ? { name: r.name } : {}),
    ...(limits ? { limits } : {}),
  };
};

const isUrl = (s: string) => /^https?:\/\//i.test(s);

/** Relative audio paths -> URLs on the worker's local media server. URLs are left untouched. */
export const rewriteAudio = (spec: VideoSpec, baseUrl: string): VideoSpec => ({
  ...spec,
  scenes: spec.scenes.map((s) =>
    s.audio && !isUrl(s.audio.src)
      ? ({
          ...s,
          audio: {
            ...s.audio,
            src: `${baseUrl}/${s.audio.src.replace(/\\/g, '/').split('/').map(encodeURIComponent).join('/')}`,
          },
        } as Scene)
      : s,
  ),
});

/** Resolves a URL path from the media server safely inside `root` (no "..", no absolute paths). */
export const safeMediaPath = (root: string, urlPath: string): string | null => {
  let rel: string;
  try {
    rel = decodeURIComponent(urlPath.split('?')[0] ?? '').replace(/^\/+/, '');
  } catch {
    return null;
  }
  const abs = path.resolve(root, rel);
  const base = path.resolve(root);
  return abs === base || !abs.startsWith(base + path.sep) ? null : abs;
};

export type QuizItem = {
  scene_id: string;
  at_s: number;
  question: string;
  options: string[];
  correct_index: number;
  countdown_s: number;
  explanation: string | null;
};

/** quiz.json: every quiz question with its start time and the explanation from the answer scene. */
export const quizJson = (spec: VideoSpec): { title: string; lang: string; questions: QuizItem[] } => {
  const questions: QuizItem[] = [];
  let t = 0;
  spec.scenes.forEach((s, i) => {
    if (s.template === 'quiz_question') {
      const next = spec.scenes[i + 1];
      questions.push({
        scene_id: s.id,
        at_s: Math.round(t * 1000) / 1000,
        question: s.question,
        options: s.options,
        correct_index: s.correct_index,
        countdown_s: s.countdown_s,
        explanation: next?.template === 'quiz_answer' ? next.explanation : null,
      });
    }
    t += s.duration_s;
  });
  return { title: spec.title, lang: spec.lang, questions };
};

/** Content hash of the Remotion sources + public assets: the bundle cache key. */
export const hashTree = (dirs: string[], extra = ''): string => {
  const h = crypto.createHash('sha256');
  h.update(extra);
  const walk = (dir: string) => {
    if (!fs.existsSync(dir)) return;
    for (const e of fs
      .readdirSync(dir, { withFileTypes: true })
      .sort((a, b) => a.name.localeCompare(b.name))) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) walk(p);
      else {
        h.update(path.relative(dir, p));
        h.update(fs.readFileSync(p));
      }
    }
  };
  for (const d of dirs) {
    h.update(`\0${path.basename(d)}\0`);
    walk(d);
  }
  return h.digest('hex').slice(0, 16);
};

/** Throttle helper for progress events: true at most every `ms`, and always for the final frame. */
export const throttle = (ms: number) => {
  let last = -Infinity;
  return (now: number, force = false): boolean => {
    if (force || now - last >= ms) {
      last = now;
      return true;
    }
    return false;
  };
};
