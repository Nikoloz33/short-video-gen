import { describe, expect, it } from 'vitest';
import { clamp, ease, frameToSec, lerp, secToFrame } from './time';

describe('time', () => {
  it('maps seconds to 30 fps frames and back', () => {
    expect(secToFrame(1)).toBe(30);
    expect(secToFrame(0.51)).toBe(15);
    expect(frameToSec(45)).toBe(1.5);
    expect(secToFrame(2, 15)).toBe(30);
  });

  it('clamps and interpolates', () => {
    expect(clamp(2)).toBe(1);
    expect(clamp(-1)).toBe(0);
    expect(lerp(10, 20, 0.25)).toBe(12.5);
  });

  it('eases stay inside [0, 1] and hit the ends', () => {
    for (const k of ['linear', 'in', 'out', 'inOut'] as const) {
      expect(ease(k, 0)).toBe(0);
      expect(ease(k, 1)).toBe(1);
      expect(ease(k, 0.5)).toBeGreaterThan(0);
      expect(ease(k, 0.5)).toBeLessThan(1);
    }
  });
});
