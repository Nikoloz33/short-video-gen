/**
 * Seconds <-> frames. The ONE place seconds become frames; pure, shared by templates and scripts.
 */
export const FPS = 30;
export const WIDTH = 1080;
export const HEIGHT = 1920;

export const secToFrame = (sec: number, fps = FPS): number => Math.round(sec * fps);
export const frameToSec = (frame: number, fps = FPS): number => frame / fps;

export const clamp = (v: number, lo = 0, hi = 1): number => Math.min(hi, Math.max(lo, v));
export const lerp = (a: number, b: number, t: number): number => a + (b - a) * t;

export type Ease = 'linear' | 'in' | 'out' | 'inOut';

export const ease = (kind: Ease, t: number): number => {
  t = clamp(t);
  switch (kind) {
    case 'linear':
      return t;
    case 'in':
      return t * t * t;
    case 'out':
      return 1 - Math.pow(1 - t, 3);
    case 'inOut':
      return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }
};
