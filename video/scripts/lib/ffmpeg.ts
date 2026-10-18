/**
 * Thin wrappers around the system ffmpeg/ffprobe (absolute path from FFMPEG_DIR, never PATH).
 * Remotion ships its own ffmpeg for rendering; this one is only for post-processing and checks.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { loadEnv } from './env';

loadEnv();

export const FFMPEG_DIR = process.env.FFMPEG_DIR ?? 'C:\\ffmpeg-7.1.1-essentials_build\\bin';
const exe = (name: string) => {
  const win = path.join(FFMPEG_DIR, `${name}.exe`);
  return process.platform === 'win32' && fs.existsSync(win) ? win : path.join(FFMPEG_DIR, name);
};
export const FFMPEG = exe('ffmpeg');
export const FFPROBE = exe('ffprobe');

export type RunResult = { code: number; stdout: string; stderr: string };

export const run = (bin: string, args: string[]): Promise<RunResult> =>
  new Promise((resolve, reject) => {
    if (!fs.existsSync(bin)) return reject(new Error(`Not found: ${bin} (set FFMPEG_DIR in .env)`));
    const p = spawn(bin, args, { windowsHide: true });
    let stdout = '';
    let stderr = '';
    p.stdout.on('data', (d) => (stdout += d));
    p.stderr.on('data', (d) => (stderr += d));
    p.on('error', reject);
    p.on('close', (code) => resolve({ code: code ?? 1, stdout, stderr }));
  });

export const runOk = async (bin: string, args: string[]): Promise<RunResult> => {
  const r = await run(bin, args);
  if (r.code !== 0) throw new Error(`${path.basename(bin)} failed (${r.code}):\n${r.stderr.slice(-2000)}`);
  return r;
};

export type Loudness = { input_i: string; input_tp: string; input_lra: string; input_thresh: string };

/** Integrated loudness (LUFS) and true peak of a file's audio, via loudnorm's analysis pass. */
export const measureLoudness = async (file: string, preFilter?: string): Promise<Loudness> => {
  const af = `${preFilter ? `${preFilter},` : ''}loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json`;
  const r = await runOk(FFMPEG, [
    '-hide_banner',
    '-nostats',
    '-i',
    file,
    '-vn',
    '-af',
    af,
    '-f',
    'null',
    '-',
  ]);
  const json = r.stderr.slice(r.stderr.lastIndexOf('{'), r.stderr.lastIndexOf('}') + 1);
  return JSON.parse(json) as Loudness;
};

export type FinalizeOptions = { durationSec: number; targetLufs?: number };

/**
 * Loudness-normalise the mixed narration to `targetLufs` (default -16, speech) with a static gain
 * and a soft limiter, then trim to the exact video length and move the moov atom up front.
 * The video stream is copied untouched. Silent inputs (no audio stream) are only remuxed.
 */
export const finalizeMp4 = async (
  input: string,
  output: string,
  opts: FinalizeOptions,
): Promise<Loudness | null> => {
  const target = opts.targetLufs ?? -16;
  const info = await probe(input);
  const common = ['-t', opts.durationSec.toFixed(3), '-movflags', '+faststart', output];
  if (info.acodec === 'none') {
    await runOk(FFMPEG, ['-hide_banner', '-y', '-i', input, '-c', 'copy', ...common]);
    return null;
  }
  const limit = 'alimiter=limit=0.8:attack=2:release=50:level=disabled';
  const chain = (gainDb: number) => `volume=${gainDb.toFixed(2)}dB,${limit}`;
  const before = await measureLoudness(input);
  const measured = Number(before.input_i);
  // A fully silent track measures -inf / -70: leave it alone instead of applying +50 dB.
  let gain = Number.isFinite(measured) && measured > -60 ? target - measured : 0;
  for (let i = 0; i < 3 && gain !== 0; i++) {
    const err = target - Number((await measureLoudness(input, chain(gain))).input_i);
    if (Math.abs(err) < 0.3) break;
    gain += err;
  }
  await runOk(FFMPEG, [
    '-hide_banner',
    '-y',
    '-i',
    input,
    '-map',
    '0:v:0',
    '-map',
    '0:a:0',
    '-c:v',
    'copy',
    '-af',
    chain(gain),
    '-ar',
    '48000',
    '-c:a',
    'aac',
    '-b:a',
    '192k',
    ...common,
  ]);
  return before;
};

export type ProbeInfo = {
  width: number;
  height: number;
  fps: number;
  duration: number;
  vcodec: string;
  acodec: string;
  sampleRate: number;
  size: number;
};

export const probe = async (file: string): Promise<ProbeInfo> => {
  const r = await runOk(FFPROBE, [
    '-v',
    'error',
    '-show_entries',
    'stream=codec_type,codec_name,width,height,r_frame_rate,sample_rate:format=duration,size',
    '-of',
    'json',
    file,
  ]);
  const j = JSON.parse(r.stdout) as {
    streams: {
      codec_type: string;
      codec_name: string;
      width?: number;
      height?: number;
      r_frame_rate?: string;
      sample_rate?: string;
    }[];
    format: { duration: string; size: string };
  };
  const v = j.streams.find((s) => s.codec_type === 'video');
  const a = j.streams.find((s) => s.codec_type === 'audio');
  const [num = 0, den = 1] = (v?.r_frame_rate ?? '0/1').split('/').map(Number);
  return {
    width: v?.width ?? 0,
    height: v?.height ?? 0,
    fps: den ? num / den : 0,
    duration: Number(j.format.duration),
    vcodec: v?.codec_name ?? 'none',
    acodec: a?.codec_name ?? 'none',
    sampleRate: Number(a?.sample_rate ?? 0),
    size: Number(j.format.size),
  };
};

/** Tile PNGs (01.png, 02.png, ...) into one contact sheet. */
export const contactSheet = async (dir: string, count: number, out: string, cols = 4): Promise<void> => {
  const rows = Math.ceil(count / cols);
  await runOk(FFMPEG, [
    '-hide_banner',
    '-y',
    '-start_number',
    '1',
    '-i',
    path.join(dir, '%02d.png'),
    '-vf',
    `scale=270:480:flags=lanczos,tile=${cols}x${rows}:padding=6:color=0x202020`,
    '-frames:v',
    '1',
    out,
  ]);
};
