import { describe, expect, it } from 'vitest';
import { parseSSE, type Snapshot } from './api';
import { quickReplies } from './components/ChatPane';
import { initialState, reducer, type State } from './reducer';
import { computeSpeed, fmtMs, fmtS } from './speed';

const ev = (s: State, event: Record<string, unknown>) =>
  reducer(s, { type: 'server', event: { type: String(event.type), ...event } });

describe('parseSSE', () => {
  it('splits events, joins data lines and keeps the partial rest', () => {
    const buf =
      'event: token\ndata: {"type":"token","text":"Hi"}\n\nevent: done\r\ndata: {"type":"done"}\r\n\r\nevent: tok';
    const { events, rest } = parseSSE(buf);
    expect(events).toEqual([{ type: 'token', text: 'Hi' }, { type: 'done' }]);
    expect(rest).toBe('event: tok');
    expect(parseSSE('data: not json\n\n').events).toEqual([]);
    expect(parseSSE(': ping\n\n').events).toEqual([]);
  });
});

describe('speed maths', () => {
  it('computes render fps, realtime factor and ETA', () => {
    const s = computeSpeed({
      stage: 'render',
      renderedFrames: 600,
      encodedFrames: 0,
      totalFrames: 1800,
      elapsedMs: 25000,
      stageMs: 20000,
      fps: 30,
    });
    expect(s.renderFps).toBe(30);
    expect(s.realtime).toBe(1);
    expect(s.etaS).toBe(40);
    expect(s.fraction).toBeCloseTo(600 / 3600);
  });

  it('handles the start and the end', () => {
    expect(
      computeSpeed({
        stage: 'render',
        renderedFrames: 0,
        encodedFrames: 0,
        totalFrames: 100,
        elapsedMs: 0,
        fps: 15,
      }).etaS,
    ).toBeNull();
    const end = computeSpeed({
      stage: 'encode',
      renderedFrames: 100,
      encodedFrames: 100,
      totalFrames: 100,
      elapsedMs: 4000,
      fps: 15,
    });
    expect(end.etaS).toBe(0);
    expect(end.fraction).toBe(1);
  });

  it('formats times', () => {
    expect(fmtS(75.4)).toBe('1:15');
    expect(fmtS(null)).toBe('—');
    expect(fmtMs(1500)).toBe('1.5s');
    expect(fmtMs(250)).toBe('250ms');
    expect(fmtMs(undefined)).toBe('—');
  });
});

describe('reducer', () => {
  it('streams tokens into one agent message and attaches cards', () => {
    let s = reducer(initialState, { type: 'user_message', text: 'make a video' });
    s = ev(s, { type: 'token', text: 'Here' });
    s = ev(s, { type: 'token', text: ' it is.' });
    s = ev(s, { type: 'card', card: { kind: 'plan' } });
    s = ev(s, { type: 'token', text: 'Next' });
    expect(s.messages.map((m) => [m.role, m.text, m.card?.kind])).toEqual([
      ['user', 'make a video', undefined],
      ['agent', 'Here it is.', 'plan'],
      ['agent', 'Next', undefined],
    ]);
  });

  it('tracks reviews, status, errors and cost', () => {
    let s = ev(initialState, { type: 'status', status: 'fact_checking' });
    s = ev(s, { type: 'awaiting_review', kind: 'script', version: 2 });
    expect(s.pending).toEqual({ kind: 'script', version: 2 });
    s = ev(s, { type: 'done', status: 'awaiting_script_review', total_cost_usd: 0.12 });
    expect(s.pending).not.toBeNull();
    expect(s.costUsd).toBe(0.12);
    s = ev(s, { type: 'done', status: 'done' });
    expect(s.pending).toBeNull();
    s = ev(s, { type: 'error', message: 'boom' });
    expect(s.error).toBe('boom');
    expect(reducer(s, { type: 'user_message', text: 'x' }).error).toBeNull();
  });

  it('follows TTS, render progress and the done event', () => {
    let s = ev(initialState, {
      type: 'render_progress',
      stage: 'tts',
      done: 2,
      total: 9,
      cache_hits: 7,
      elapsedMs: 900,
    });
    expect(s.render?.stage).toBe('tts');
    expect(s.render?.tts.cache_hits).toBe(7);
    s = ev(s, {
      type: 'render_progress',
      preset: 'preview',
      version: 3,
      stage: 'render',
      renderedFrames: 10,
      totalFrames: 100,
      elapsedMs: 2000,
      stageMs: 1000,
    });
    expect(s.render).toMatchObject({ preset: 'preview', version: 3, renderedFrames: 10, totalFrames: 100 });
    s = ev(s, {
      type: 'render_done',
      preset: 'preview',
      version: 3,
      totalFrames: 100,
      durationMs: 9000,
      stages: { render_ms: 5000 },
      cacheHits: { bundle: true },
    });
    expect(s.render).toMatchObject({ finished: true, bundleCacheHit: true, stage: 'done' });
    expect(s.selectedVersion).toBe(3);
    // A new render after a finished one starts fresh.
    s = ev(s, {
      type: 'render_progress',
      preset: 'final',
      version: 3,
      stage: 'render',
      renderedFrames: 1,
      totalFrames: 200,
    });
    expect(s.render).toMatchObject({ preset: 'final', finished: false, renderedFrames: 1 });
    expect(ev(initialState, { type: 'render_done' })).toBe(initialState);
    expect(ev(initialState, { type: 'unknown' })).toBe(initialState);
  });

  it('loads a snapshot and picks the latest rendered version', () => {
    const snap: Snapshot = {
      project: { id: 'p1', title: 'T' },
      status: 'done',
      messages: [{ role: 'agent', text: 'hi', card: { kind: 'done' } }],
      pending: null,
      spec: null,
      versions: [
        { version: 1, preview: { mp4: true }, final: null },
        { version: 2, preview: { mp4: true }, final: { mp4: true } },
        { version: 3, preview: null, final: null },
      ],
      sources: [],
      cost_usd: 0.3,
    };
    const s = reducer(initialState, { type: 'loaded', snapshot: snap });
    expect(s).toMatchObject({ projectId: 'p1', selectedVersion: 2, preset: 'final', costUsd: 0.3 });
    expect(reducer(s, { type: 'select_version', version: 1 }).selectedVersion).toBe(1);
    expect(reducer(s, { type: 'select_preset', preset: 'preview' }).preset).toBe('preview');
    expect(reducer(s, { type: 'versions', versions: [] }).selectedVersion).toBe(2);
    expect(reducer(s, { type: 'busy', busy: true }).busy).toBe(true);
    expect(reducer(s, { type: 'system_message', text: 'x' }).messages.at(-1)?.role).toBe('system');
  });
});

describe('quick replies', () => {
  it('match the pending checkpoint and offer the other language', () => {
    expect(quickReplies(null, 'ka')).toEqual([]);
    const script = quickReplies({ kind: 'script' }, 'ka');
    expect(script[0]).toEqual({ label: 'Approve script', action: 'approve' });
    expect(script.map((r) => r.label)).toContain('Switch to English');
    const video = quickReplies({ kind: 'video' }, 'en');
    expect(video[0]!.label).toBe('Approve final video');
    expect(video.find((r) => r.label === 'Switch to Georgian')?.text).toMatch(/Georgian/);
  });
});
