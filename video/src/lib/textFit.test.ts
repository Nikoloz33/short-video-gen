import { describe, expect, it } from 'vitest';
import { fitSize, fitText, measure, missingGlyphs, segmentLines, stripMarkup } from './textFit';

const box = { width: 600, maxLines: 2, size: 50, weight: 400 as const };

describe('measure', () => {
  it('is additive and scales with size', () => {
    const a = measure('Wash', 50);
    expect(measure('WashWash', 50)).toBeCloseTo(2 * a, 6);
    expect(measure('Wash', 100)).toBeCloseTo(2 * a, 6);
  });

  it('bold is wider than regular for the same text', () => {
    expect(measure('Wash your hands', 50, 700)).toBeGreaterThan(measure('Wash your hands', 50, 400));
  });

  it('measures Georgian from the Georgian face', () => {
    expect(measure('ხელები', 50)).toBeGreaterThan(100);
    expect(missingGlyphs('დაიბანეთ ხელები 20 წამი')).toEqual([]);
  });

  it('ignores highlight markers', () => {
    expect(measure('*soap*', 50)).toBe(measure('soap', 50));
    expect(stripMarkup('use *soap* now')).toBe('use soap now');
  });
});

describe('fitText', () => {
  it('wraps greedily into lines', () => {
    const r = fitText('Wet your hands with clean running water', box);
    expect(r.ok).toBe(true);
    expect(r.lines.length).toBe(2);
    expect(r.lines.join(' ')).toBe('Wet your hands with clean running water');
    for (const l of r.lines) expect(measure(l, 50)).toBeLessThanOrEqual(600);
  });

  it('honours explicit line breaks', () => {
    expect(fitText('Step one\nStep two', box).lines).toEqual(['Step one', 'Step two']);
  });

  it('reports too many lines as overflow, not truncation', () => {
    const r = fitText(
      'Wet your hands with clean running water and apply enough soap to cover all surfaces',
      box,
    );
    expect(r.ok).toBe(false);
    expect(r.reason).toBe('overflow_lines');
    expect(r.lines.length).toBeGreaterThan(2);
  });

  it('reports a single word wider than the box', () => {
    const r = fitText('Supercalifragilisticexpialidocious', { ...box, width: 300 });
    expect(r.reason).toBe('overflow_word');
  });

  it('reports glyphs the bundled fonts cannot draw', () => {
    const r = fitText('Done ✓ 好', box);
    expect(r.reason).toBe('missing_glyph');
    expect(r.missing).toEqual(['✓', '好']);
  });

  it('rejects empty text', () => {
    expect(fitText('  ** ', box).reason).toBe('empty');
  });

  it('fits Georgian text (wider glyphs: ~0.6 em per letter)', () => {
    const text = 'დაიბანეთ ხელები თბილი წყლით და საპნით';
    expect(fitText(text, box).reason).toBe('overflow_lines');
    const r = fitText(text, { ...box, maxLines: 3 });
    expect(r.ok).toBe(true);
    expect(r.lines).toHaveLength(3);
  });
});

describe('fitSize', () => {
  it('steps the size down until the text fits', () => {
    const text = 'Wet your hands with clean running water and apply soap';
    expect(fitText(text, box).ok).toBe(false);
    const r = fitSize(text, box, 30);
    expect(r?.ok).toBe(true);
    expect(r!.size).toBeLessThan(50);
  });

  it('returns null when nothing fits', () => {
    expect(fitSize('word '.repeat(80), box, 40)).toBeNull();
    expect(fitSize('好', box, 20)).toBeNull();
  });
});

describe('segmentLines', () => {
  it('carries highlights across line breaks', () => {
    expect(segmentLines(['use *warm', 'water* now'])).toEqual([
      [
        { text: 'use ', hl: false },
        { text: 'warm', hl: true },
      ],
      [
        { text: 'water', hl: true },
        { text: ' now', hl: false },
      ],
    ]);
  });
});

describe('fitShrink', () => {
  it('keeps the box size when the text fits and shrinks long words up to 80 %', async () => {
    const { fitShrink, MIN_SHRINK } = await import('./textFit');
    const title = { width: 920, maxLines: 3, size: 92, weight: 700 as const };
    expect(fitShrink('How to wash your hands', title).size).toBe(92);
    const long = 'ხელის დაბანა კვების პერსონალისთვის';
    expect(fitText(long, title).ok).toBe(false);
    const r = fitShrink(long, title);
    expect(r.ok).toBe(true);
    expect(r.size).toBeLessThan(92);
    expect(r.size).toBeGreaterThanOrEqual(Math.round(92 * MIN_SHRINK));
    expect(fitShrink('word '.repeat(60), title).ok).toBe(false);
  });
});
