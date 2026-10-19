/**
 * Render worker — the agent's only way to render. Reads ONE JSON request on stdin, writes JSON lines
 * on stdout (all logs go to stderr):
 *
 *   {"cmd":"check","spec":{...}}
 *     -> {"type":"check","ok":true,"issues":[]}
 *   {"cmd":"render","spec":{...},"preset":"preview"|"final","out_dir":"...","media_root":"...",
 *    "concurrency":15,"timeout_s":300,"name":"video"}
 *     -> {"type":"progress","stage":"validate"|"bundle"|"render"|"encode"|"post",
 *         "renderedFrames","encodedFrames","totalFrames","elapsedMs","stageMs"}   (many)
 *     -> {"type":"done","mp4","srt","vtt","quiz","meta","durationMs","stages":{...},"probe":{...},
 *         "checks":[...],"cacheHits":{...}}
 *   on failure: {"type":"error","code","message","issues"?} and a non-zero exit code
 *   (2 invalid request/spec, 3 timeout, 1 anything else).
 *
 * The bundle is cached on disk by a content hash of src/ + public/, so only the first render after a
 * template change pays for webpack.
 */
import fs from 'node:fs';
import http from 'node:http';
import type { AddressInfo } from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { makeCancelSignal, renderMedia, selectComposition } from '@remotion/renderer';
import { z } from 'zod';
import { VideoSpecSchema } from '../src/generated/spec.zod';
import { videoCues, toSrt, toVtt } from '../src/lib/captions';
import { checkSpec, DEFAULT_LIMITS, type CheckLimits } from '../src/lib/checkSpec';
import type { VideoSpec } from '../src/spec/types';
import { VIDEO_ROOT } from './lib/bundle';
import { finalizeMp4, probe } from './lib/ffmpeg';
import {
  COMPOSITION,
  PRESETS,
  defaultConcurrency,
  RequestError,
  hashTree,
  parseRequest,
  quizJson,
  rewriteAudio,
  safeMediaPath,
  throttle,
  type RenderRequest,
} from './lib/worker-lib';

// stdout is the protocol channel: route every stray log to stderr.
const out = process.stdout.write.bind(process.stdout);
console.log = (...a: unknown[]) => process.stderr.write(a.map(String).join(' ') + '\n');
console.info = console.log;
const emit = (event: Record<string, unknown>) => out(JSON.stringify(event) + '\n');

const fail = (code: string, message: string, exit: number, extra: Record<string, unknown> = {}): never => {
  emit({ type: 'error', code, message, ...extra });
  process.exit(exit);
};

const readStdin = async (): Promise<string> => {
  const chunks: Buffer[] = [];
  for await (const c of process.stdin) chunks.push(c as Buffer);
  return Buffer.concat(chunks).toString('utf8');
};

const validate = (
  raw: unknown,
  limits: Partial<CheckLimits> = {},
): { spec: VideoSpec; issues: ReturnType<typeof checkSpec> } => {
  const parsed = VideoSpecSchema.safeParse(raw);
  if (!parsed.success) {
    return fail('invalid_spec', z.prettifyError(parsed.error), 2, {
      issues: parsed.error.issues.map((i) => ({ path: i.path.join('.'), message: i.message })),
    });
  }
  const spec = parsed.data as VideoSpec;
  return { spec, issues: checkSpec(spec, { ...DEFAULT_LIMITS, ...limits }) };
};

/** Bundle once per content hash; later renders reuse the directory (cache hit). */
const cachedBundle = async (onProgress: (pct: number) => void): Promise<{ dir: string; hit: boolean }> => {
  const pkg = fs.readFileSync(path.join(VIDEO_ROOT, 'package.json'), 'utf8');
  const key = hashTree([path.join(VIDEO_ROOT, 'src'), path.join(VIDEO_ROOT, 'public')], pkg);
  const root = path.join(VIDEO_ROOT, '..', 'out', '.bundle-cache');
  const dir = path.join(root, key);
  if (fs.existsSync(path.join(dir, 'index.html'))) return { dir, hit: true };
  fs.mkdirSync(root, { recursive: true });
  for (const old of fs.readdirSync(root))
    if (old !== key) fs.rmSync(path.join(root, old), { recursive: true, force: true });
  const { bundle } = await import('@remotion/bundler');
  const tmp = `${dir}.tmp-${process.pid}`;
  await bundle({
    entryPoint: path.join(VIDEO_ROOT, 'src', 'index.ts'),
    publicDir: path.join(VIDEO_ROOT, 'public'),
    outDir: tmp,
    onProgress,
  });
  fs.rmSync(dir, { recursive: true, force: true });
  fs.renameSync(tmp, dir);
  return { dir, hit: false };
};

/** Tiny static file server for narration clips (Chromium + Remotion fetch audio over http). */
const serveMedia = (root: string): Promise<{ url: string; close: () => void }> =>
  new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const file = safeMediaPath(root, req.url ?? '/');
      if (!file || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
        res.writeHead(404).end();
        return;
      }
      const type = file.endsWith('.wav')
        ? 'audio/wav'
        : file.endsWith('.mp3')
          ? 'audio/mpeg'
          : 'application/octet-stream';
      res.writeHead(200, {
        'content-type': type,
        'content-length': fs.statSync(file).size,
        'access-control-allow-origin': '*',
      });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address() as AddressInfo;
      resolve({ url: `http://127.0.0.1:${port}`, close: () => server.close() });
    });
  });

const render = async (req: RenderRequest) => {
  const t0 = Date.now();
  const stages: Record<string, number> = {};
  const preset = PRESETS[req.preset];
  const progress = (stage: string, extra: Record<string, unknown> = {}) =>
    emit({ type: 'progress', stage, elapsedMs: Date.now() - t0, ...extra });

  let stageStart = Date.now();
  progress('validate');
  const { spec, issues } = validate(req.spec, req.limits);
  if (issues.length) fail('layout_check_failed', `${issues.length} layout issue(s)`, 2, { issues });
  stages.validate_ms = Date.now() - stageStart;

  const { cancelSignal, cancel } = makeCancelSignal();
  const timeoutS = req.timeout_s ?? 600;
  const timer = setTimeout(() => {
    cancel();
    fail('timeout', `render exceeded ${timeoutS} s`, 3);
  }, timeoutS * 1000);

  stageStart = Date.now();
  progress('bundle');
  const tick = throttle(250);
  const { dir: serveUrl, hit: bundleHit } = await cachedBundle((pct) => {
    if (tick(Date.now(), pct === 100)) progress('bundle', { percent: pct });
  });
  stages.bundle_ms = Date.now() - stageStart;

  const media = req.media_root ? await serveMedia(req.media_root) : null;
  const inputProps = media ? rewriteAudio(spec, media.url) : spec;

  fs.mkdirSync(req.out_dir, { recursive: true });
  const name = req.name ?? 'video';
  const raw = path.join(req.out_dir, `.raw-${name}.mp4`);
  const mp4 = path.join(req.out_dir, `${name}.mp4`);
  const totalSec = spec.scenes.reduce((n, s) => n + s.duration_s, 0);

  try {
    const composition = await selectComposition({
      serveUrl,
      id: COMPOSITION[req.preset],
      inputProps: inputProps as unknown as Record<string, unknown>,
      logLevel: 'error',
    });
    const totalFrames = composition.durationInFrames;
    stageStart = Date.now();
    let renderDone = 0;
    const rtick = throttle(250);
    await renderMedia({
      composition,
      serveUrl,
      inputProps: inputProps as unknown as Record<string, unknown>,
      codec: 'h264',
      outputLocation: raw,
      overwrite: true,
      scale: preset.scale,
      crf: preset.crf,
      x264Preset: preset.x264,
      pixelFormat: 'yuv420p',
      imageFormat: 'jpeg',
      jpegQuality: preset.jpegQuality,
      audioCodec: 'aac',
      concurrency: req.concurrency ?? defaultConcurrency(os.cpus().length),
      // Always mux an AAC track (silent when a spec has no narration yet) so outputs are uniform.
      enforceAudioTrack: true,
      cancelSignal,
      logLevel: 'error',
      licenseKey: process.env.REMOTION_LICENSE_KEY || null,
      onProgress: ({ renderedFrames, encodedFrames, stitchStage }) => {
        if (!renderDone && renderedFrames >= totalFrames) renderDone = Date.now();
        const done = encodedFrames >= totalFrames;
        if (rtick(Date.now(), done)) {
          progress(renderedFrames < totalFrames ? 'render' : 'encode', {
            renderedFrames,
            encodedFrames,
            totalFrames,
            stitchStage,
            stageMs: Date.now() - stageStart,
          });
        }
      },
    });
    const end = Date.now();
    stages.render_ms = (renderDone || end) - stageStart;
    stages.encode_ms = end - (renderDone || end);

    stageStart = Date.now();
    progress('post');
    await finalizeMp4(raw, mp4, {
      durationSec: totalSec,
      targetLufs: -16,
      normalize: preset.normalizeLoudness,
    });
    fs.rmSync(raw, { force: true });

    const cues = videoCues(spec.scenes);
    const files = {
      srt: path.join(req.out_dir, `${name}.srt`),
      vtt: path.join(req.out_dir, `${name}.vtt`),
      quiz: path.join(req.out_dir, 'quiz.json'),
      meta: path.join(req.out_dir, 'meta.json'),
    };
    fs.writeFileSync(files.srt, toSrt(cues));
    fs.writeFileSync(files.vtt, toVtt(cues));
    fs.writeFileSync(files.quiz, JSON.stringify(quizJson(spec), null, 2) + '\n');
    const info = await probe(mp4);
    stages.post_ms = Date.now() - stageStart;

    const expectW = preset.width;
    const expectH = preset.height;
    const checks = [
      {
        name: 'resolution',
        ok: info.width === expectW && info.height === expectH,
        detail: `${info.width}x${info.height}`,
      },
      { name: 'fps', ok: Math.abs(info.fps - preset.fps) < 0.01, detail: String(info.fps) },
      {
        name: 'duration',
        ok: Math.abs(info.duration - totalSec) <= 0.3,
        detail: `${info.duration.toFixed(3)} s (planned ${totalSec.toFixed(3)} s)`,
      },
      {
        name: 'codecs',
        ok: info.vcodec === 'h264' && info.acodec === 'aac',
        detail: `${info.vcodec}/${info.acodec}`,
      },
      { name: 'captions', ok: cues.length > 0, detail: `${cues.length} cues` },
    ];
    const durationMs = Date.now() - t0;
    const meta = {
      file: path.basename(mp4),
      title: spec.title,
      lang: spec.lang,
      version: spec.version,
      preset: req.preset,
      duration_s: info.duration,
      sources: spec.sources,
      stages,
      render_fps: totalFrames / Math.max(0.001, stages.render_ms / 1000),
      realtime_factor: totalSec / Math.max(0.001, durationMs / 1000),
    };
    fs.writeFileSync(files.meta, JSON.stringify(meta, null, 2) + '\n');
    emit({
      type: 'done',
      mp4,
      ...files,
      durationMs,
      totalFrames,
      stages,
      probe: info,
      checks,
      cacheHits: { bundle: bundleHit },
    });
    if (checks.some((c) => !c.ok)) process.exitCode = 1;
  } finally {
    clearTimeout(timer);
    media?.close();
  }
};

const main = async () => {
  let req;
  try {
    req = parseRequest(await readStdin());
  } catch (e) {
    return fail('bad_request', e instanceof RequestError ? e.message : String(e), 2);
  }
  if (req.cmd === 'check') {
    const { issues } = validate(req.spec, req.limits);
    emit({ type: 'check', ok: issues.length === 0, issues });
    return;
  }
  await render(req);
};

main().then(
  () => process.exit(process.exitCode ?? 0),
  (e: unknown) => fail('render_failed', e instanceof Error ? e.message : String(e), 1),
);
