import { describe, expect, it } from 'vitest';
import { galleryScene } from '../examples/gallery';
import type { Scene } from '../spec/types';
import { CAPTION_BOX } from '../templates/boxes';
import { chunkText, NO_AUDIO_LEAD_S, sceneCues, toSrt, toVtt, videoCues } from './captions';
import { fitText } from './textFit';

const withAudio = (s: Scene, start: number, dur: number): Scene => ({
  ...s,
  audio: { src: 'x.wav', start_s: start, duration_s: dur },
});

describe('chunkText', () => {
  it('keeps sentences apart and every chunk fits the caption band', () => {
    const text =
      'Wet your hands with clean running water. Apply enough soap to cover all hand surfaces, then scrub the backs of your hands, between your fingers and under your nails!';
    const chunks = chunkText(text);
    expect(chunks[0]).toBe('Wet your hands with clean running water.');
    expect(chunks.length).toBeGreaterThan(2);
    for (const c of chunks) expect(fitText(c, CAPTION_BOX).ok).toBe(true);
    expect(chunks.join(' ')).toBe(text);
  });

  it('strips highlight markup and collapses whitespace', () => {
    expect(chunkText('Use  *warm*\nwater.')).toEqual(['Use warm water.']);
  });

  it('chunks Georgian', () => {
    const chunks = chunkText(
      'დაწყებამდე მოიხსენით ბეჭდები და საათი, აიკეცეთ სახელოები და შეამოწმეთ, არის თუ არა საპონი.',
    );
    expect(chunks.length).toBeGreaterThanOrEqual(1);
    for (const c of chunks) expect(fitText(c, CAPTION_BOX).ok).toBe(true);
  });
});

describe('cues', () => {
  it('spread over the measured clip, proportional to length', () => {
    const s = withAudio(galleryScene('en', 'checklist'), 0.4, 5);
    const cues = sceneCues(s);
    expect(cues[0]!.start).toBeCloseTo(0.4);
    expect(cues.at(-1)!.end).toBeCloseTo(5.4);
    for (let i = 1; i < cues.length; i++) expect(cues[i]!.start).toBeCloseTo(cues[i - 1]!.end);
  });

  it('fall back to the scene duration without audio', () => {
    const s = galleryScene('en', 'title_card');
    const cues = sceneCues(s);
    expect(cues[0]!.start).toBe(NO_AUDIO_LEAD_S);
    expect(cues.at(-1)!.end).toBeLessThan(s.duration_s);
  });

  it('offset by preceding scenes for the whole video', () => {
    const a = withAudio(galleryScene('en', 'title_card'), 0.3, 3);
    const b = withAudio(galleryScene('en', 'step_card'), 0.3, 3);
    const cues = videoCues([a, b]);
    const firstOfB = cues.find((c) => c.text.startsWith('Step one'));
    expect(firstOfB!.start).toBeCloseTo(a.duration_s + 0.3);
  });
});

describe('srt / vtt', () => {
  const cues = [
    { start: 0.3, end: 2.05, text: 'Hello there', lines: ['Hello there'] },
    { start: 62.5, end: 3725.001, text: 'two lines', lines: ['two', 'lines'] },
  ];
  it('formats SRT', () => {
    expect(toSrt(cues)).toBe(
      '1\n00:00:00,300 --> 00:00:02,050\nHello there\n\n2\n00:01:02,500 --> 01:02:05,001\ntwo\nlines\n',
    );
  });
  it('formats WebVTT', () => {
    expect(toVtt(cues).startsWith('WEBVTT\n\n00:00:00.300 --> 00:00:02.050\nHello there\n')).toBe(true);
  });
});
