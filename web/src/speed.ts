/** Render-speed maths shown in the panel (pure, unit tested). */

export type Progress = {
  stage: string;
  renderedFrames: number;
  encodedFrames: number;
  totalFrames: number;
  /** ms since the render request started (worker clock). */
  elapsedMs: number;
  /** ms since the render stage started, if known. */
  stageMs?: number;
  fps: number;
};

export type Speed = {
  /** frames rendered per wall-clock second */
  renderFps: number;
  /** seconds of video rendered per wall second */
  realtime: number;
  /** seconds left, null when unknown */
  etaS: number | null;
  /** 0..1 */
  fraction: number;
};

export const computeSpeed = (p: Progress): Speed => {
  const done =
    p.stage === 'render' ? p.renderedFrames : Math.min(p.renderedFrames, p.encodedFrames || p.renderedFrames);
  const ms = p.stageMs && p.stageMs > 0 ? p.stageMs : p.elapsedMs;
  const sec = ms / 1000;
  const renderFps = sec > 0 ? p.renderedFrames / sec : 0;
  const realtime = p.fps > 0 ? renderFps / p.fps : 0;
  const total = Math.max(1, p.totalFrames);
  const fraction = Math.min(1, Math.max(0, (p.renderedFrames + (p.encodedFrames || 0)) / (2 * total)));
  const left = total - done;
  const etaS = renderFps > 0 && left > 0 ? left / renderFps : left <= 0 ? 0 : null;
  return { renderFps, realtime, etaS, fraction };
};

export const fmtS = (s: number | null | undefined): string => {
  if (s === null || s === undefined || !Number.isFinite(s)) return '—';
  const t = Math.max(0, Math.round(s));
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, '0')}`;
};

export const fmtMs = (ms: number | undefined): string =>
  ms === undefined ? '—' : ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
