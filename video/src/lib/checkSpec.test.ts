import { describe, expect, it } from 'vitest';
import { galleryReel, galleryScene, TEMPLATES } from '../examples/gallery';
import type { Scene, VideoSpec } from '../spec/types';
import { checkSpec, DEFAULT_LIMITS } from './checkSpec';

const loose = { ...DEFAULT_LIMITS, minTotalS: 0, maxTotalS: 999 };
const spec = (scenes: Scene[], extra: Partial<VideoSpec> = {}): VideoSpec => ({
  ...galleryReel('en'),
  audience: 'workplace',
  scenes,
  ...extra,
});
const codes = (s: VideoSpec) => checkSpec(s, loose).map((i) => i.code);

describe('checkSpec', () => {
  it('accepts every gallery template in both languages', () => {
    for (const lang of ['en', 'ka'] as const) {
      expect(checkSpec(galleryReel(lang), { ...loose })).toEqual([]);
    }
  });

  it('flags text that overflows its box, with the field and index', () => {
    const s = galleryScene('en', 'checklist');
    if (s.template !== 'checklist') throw new Error();
    s.items = [
      'ok',
      'This checklist item is far too long to fit inside two lines of the checklist row box ever',
    ];
    const issues = checkSpec(spec([s]), loose);
    expect(issues).toHaveLength(1);
    expect(issues[0]).toMatchObject({
      scene_id: s.id,
      field: 'items',
      index: 1,
      code: 'text_overflow_lines',
    });
  });

  it('flags glyphs the fonts cannot draw (text and narration)', () => {
    const s = galleryScene('en', 'step_card');
    if (s.template !== 'step_card') throw new Error();
    s.text = 'Wash ✓';
    s.narration = 'Done ✓.';
    expect(codes(spec([s]))).toEqual(['text_missing_glyph', 'caption_missing_glyph']);
  });

  it('flags unknown icons', () => {
    const s = galleryScene('en', 'do_dont');
    if (s.template !== 'do_dont') throw new Error();
    s.dont_icon = 'mittens';
    const issues = checkSpec(spec([s]), loose);
    expect(issues[0]).toMatchObject({ field: 'dont_icon', code: 'unknown_icon' });
  });

  it('flags durations outside the limits', () => {
    const s = { ...galleryScene('en', 'title_card'), duration_s: 1 };
    expect(codes(spec([s]))).toContain('scene_duration');
    expect(checkSpec(spec([galleryScene('en', 'title_card')])).map((i) => i.code)).toContain(
      'total_duration',
    );
  });

  it('flags narration audio longer than its scene', () => {
    const s = { ...galleryScene('en', 'title_card'), audio: { src: 'a.wav', start_s: 0.3, duration_s: 4 } };
    expect(codes(spec([s]))).toContain('audio_overruns_scene');
  });

  it('checks quiz answers and reading time', () => {
    const q = galleryScene('en', 'quiz_question');
    if (q.template !== 'quiz_question') throw new Error();
    q.correct_index = 3;
    q.countdown_s = 7;
    expect(codes(spec([q]))).toEqual(['bad_correct_index', 'quiz_read_time']);
  });

  it('checks step numbers and duplicate ids', () => {
    const s = galleryScene('en', 'step_card');
    if (s.template !== 'step_card') throw new Error();
    s.step_no = 7;
    expect(codes(spec([s, { ...s }]))).toEqual(['bad_step_no', 'duplicate_id', 'bad_step_no']);
  });

  it('requires a disclaimer in patient videos', () => {
    const scenes = TEMPLATES.filter((t) => t !== 'disclaimer').map((t) => galleryScene('en', t));
    expect(codes(spec(scenes, { audience: 'patient' }))).toEqual(['missing_disclaimer']);
    expect(codes(spec(scenes, { audience: 'workplace' }))).toEqual([]);
  });

  it('rejects an empty spec', () => {
    expect(codes(spec([]))).toEqual(['no_scenes']);
  });
});
