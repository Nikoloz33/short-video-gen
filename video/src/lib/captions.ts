/**
 * Narration -> caption cues. The burned-in caption band and the exported SRT/VTT use these same
 * cues, so they are always in sync. Without word timestamps, each chunk gets a share of the
 * measured clip duration proportional to its length.
 */
import type { Scene } from '../spec/types';
import { CAPTION_BOX } from '../templates/boxes';
import { fitText, stripMarkup, type FitBox } from './textFit';

export type Cue = { start: number; end: number; text: string; lines: string[] };

/** Without audio (previews before TTS) captions run from 0.3 s to 0.5 s before the scene ends. */
export const NO_AUDIO_LEAD_S = 0.3;
export const NO_AUDIO_TAIL_S = 0.5;

/** Splits text into sentences, then packs words into chunks that fit `box`. */
export const chunkText = (text: string, box: FitBox = CAPTION_BOX): string[] => {
  const sentences = stripMarkup(text)
    .replace(/\s+/g, ' ')
    .trim()
    .split(/(?<=[.!?;])\s+/)
    .filter(Boolean);
  const chunks: string[] = [];
  for (const sentence of sentences) {
    let cur = '';
    for (const word of sentence.split(' ')) {
      const candidate = cur ? `${cur} ${word}` : word;
      if (cur && !fitText(candidate, box).ok) {
        chunks.push(cur);
        cur = word;
      } else {
        cur = candidate;
      }
    }
    if (cur) chunks.push(cur);
  }
  return chunks;
};

/** Cues for one scene, in seconds relative to the scene start. */
export const sceneCues = (scene: Scene): Cue[] => {
  const start = scene.audio ? scene.audio.start_s : NO_AUDIO_LEAD_S;
  const dur = scene.audio
    ? scene.audio.duration_s
    : Math.max(0.5, scene.duration_s - NO_AUDIO_LEAD_S - NO_AUDIO_TAIL_S);
  const chunks = chunkText(scene.narration);
  const total = chunks.reduce((n, c) => n + c.length, 0) || 1;
  let t = start;
  return chunks.map((text) => {
    const len = (dur * text.length) / total;
    const cue = { start: t, end: t + len, text, lines: fitText(text, CAPTION_BOX).lines };
    t += len;
    return cue;
  });
};

/** Cues for the whole video, in seconds from the video start. */
export const videoCues = (scenes: Scene[]): Cue[] => {
  let offset = 0;
  const out: Cue[] = [];
  for (const s of scenes) {
    for (const c of sceneCues(s)) out.push({ ...c, start: c.start + offset, end: c.end + offset });
    offset += s.duration_s;
  }
  return out;
};

const pad = (n: number, w = 2) => String(n).padStart(w, '0');
const stamp = (sec: number, sep: ',' | '.') => {
  const ms = Math.round(sec * 1000);
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  const s = Math.floor((ms % 60_000) / 1000);
  return `${pad(h)}:${pad(m)}:${pad(s)}${sep}${pad(ms % 1000, 3)}`;
};

export const toSrt = (cues: Cue[]): string =>
  cues
    .map((c, i) => `${i + 1}\n${stamp(c.start, ',')} --> ${stamp(c.end, ',')}\n${c.lines.join('\n')}\n`)
    .join('\n');

export const toVtt = (cues: Cue[]): string =>
  `WEBVTT\n\n${cues.map((c) => `${stamp(c.start, '.')} --> ${stamp(c.end, '.')}\n${c.lines.join('\n')}\n`).join('\n')}`;
