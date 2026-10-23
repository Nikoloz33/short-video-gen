/** All UI state comes from server events through this reducer (no state library). */
import type { Card, ServerEvent, Snapshot, SpecOutline, VersionInfo } from './api';

export type Message = { id: number; role: 'user' | 'agent' | 'system'; text: string; card?: Card | null };

export type RenderState = {
  preset: 'preview' | 'final';
  version: number | null;
  stage: string;
  renderedFrames: number;
  encodedFrames: number;
  totalFrames: number;
  elapsedMs: number;
  stageMs?: number;
  startedAt: number;
  stages: Record<string, number>;
  tts: {
    done?: number;
    total?: number;
    cache_hits?: number;
    ms?: number;
    synthesized?: number;
    clips?: number;
  };
  bundleCacheHit: boolean | null;
  finished: boolean;
  /** Set when the run ends without finishing this render (error, review, stop): freezes the clock. */
  endedAt?: number;
};

export type State = {
  projectId: string | null;
  messages: Message[];
  status: string;
  busy: boolean;
  pending: { kind: 'script' | 'video'; version?: number } | null;
  render: RenderState | null;
  versions: VersionInfo[];
  selectedVersion: number | null;
  preset: 'preview' | 'final';
  error: string | null;
  costUsd: number;
  canRetry: boolean;
  spec: SpecOutline | null;
  nextId: number;
};

export const initialState: State = {
  projectId: null,
  messages: [],
  status: 'idle',
  busy: false,
  pending: null,
  render: null,
  versions: [],
  selectedVersion: null,
  preset: 'preview',
  error: null,
  costUsd: 0,
  canRetry: false,
  spec: null,
  nextId: 1,
};

export type Action =
  | { type: 'loaded'; snapshot: Snapshot }
  | { type: 'user_message'; text: string }
  | { type: 'system_message'; text: string; card?: Card }
  | { type: 'busy'; busy: boolean }
  | { type: 'server'; event: ServerEvent }
  | { type: 'select_version'; version: number }
  | { type: 'select_preset'; preset: 'preview' | 'final' }
  | { type: 'versions'; versions: VersionInfo[]; spec?: SpecOutline | null }
  | { type: 'error'; message: string };

const num = (v: unknown, d = 0): number => (typeof v === 'number' && Number.isFinite(v) ? v : d);

const latest = (versions: VersionInfo[]): number | null => {
  const rendered = versions.filter((v) => v.preview || v.final);
  return rendered.length ? rendered[rendered.length - 1]!.version : null;
};

const pushAgentText = (s: State, text: string): State => {
  const last = s.messages[s.messages.length - 1];
  // Tokens extend the last agent message until a card closes it.
  if (last && last.role === 'agent' && !last.card) {
    const messages = s.messages.slice(0, -1).concat({ ...last, text: last.text + text });
    return { ...s, messages };
  }
  return { ...s, messages: [...s.messages, { id: s.nextId, role: 'agent', text }], nextId: s.nextId + 1 };
};

const attachCard = (s: State, card: Card): State => {
  const last = s.messages[s.messages.length - 1];
  if (last && last.role === 'agent' && !last.card) {
    return { ...s, messages: s.messages.slice(0, -1).concat({ ...last, card }) };
  }
  return {
    ...s,
    messages: [...s.messages, { id: s.nextId, role: 'agent', text: '', card }],
    nextId: s.nextId + 1,
  };
};

const onServer = (s: State, e: ServerEvent): State => {
  switch (e.type) {
    case 'token':
      return pushAgentText(s, String(e.text ?? ''));
    case 'card':
      return attachCard(s, e.card as Card);
    case 'status':
      return { ...s, status: String(e.status) };
    case 'awaiting_review':
      return { ...s, pending: { kind: e.kind as 'script' | 'video', version: num(e.version) } };
    case 'render_progress': {
      const prev = s.render;
      const preset = (e.preset as 'preview' | 'final' | undefined) ?? prev?.preset ?? 'preview';
      const version = e.version !== undefined ? num(e.version) : (prev?.version ?? null);
      const fresh = !prev || prev.finished || prev.preset !== preset || prev.version !== version;
      const base: RenderState = fresh
        ? {
            preset,
            version,
            stage: 'tts',
            renderedFrames: 0,
            encodedFrames: 0,
            totalFrames: 0,
            elapsedMs: 0,
            startedAt: Date.now(),
            stages: {},
            tts: prev && !prev.finished ? prev.tts : {},
            bundleCacheHit: null,
            finished: false,
          }
        : prev;
      if (e.stage === 'tts') {
        return {
          ...s,
          render: {
            ...base,
            stage: 'tts',
            tts: {
              ...base.tts,
              done: num(e.done),
              total: num(e.total),
              cache_hits: num(e.cache_hits),
              ms: num(e.elapsedMs),
            },
          },
        };
      }
      const tts = (e.tts as RenderState['tts'] | undefined) ?? base.tts;
      return {
        ...s,
        render: {
          ...base,
          tts: { ...base.tts, ...tts },
          stage: String(e.stage),
          renderedFrames: num(e.renderedFrames, base.renderedFrames),
          encodedFrames: num(e.encodedFrames, base.encodedFrames),
          totalFrames: num(e.totalFrames, base.totalFrames),
          elapsedMs: num(e.elapsedMs, base.elapsedMs),
          stageMs: e.stageMs !== undefined ? num(e.stageMs) : base.stageMs,
        },
      };
    }
    case 'render_done': {
      const prev = s.render;
      if (!prev) return s;
      return {
        ...s,
        render: {
          ...prev,
          stage: 'done',
          finished: true,
          stages: (e.stages as Record<string, number>) ?? {},
          renderedFrames: num(e.totalFrames, prev.renderedFrames),
          encodedFrames: num(e.totalFrames, prev.encodedFrames),
          totalFrames: num(e.totalFrames, prev.totalFrames),
          elapsedMs: num(e.durationMs, prev.elapsedMs),
          bundleCacheHit: Boolean((e.cacheHits as { bundle?: boolean } | undefined)?.bundle),
          tts: { ...prev.tts, ...((e.tts as RenderState['tts']) ?? {}) },
        },
        selectedVersion: num(e.version, s.selectedVersion ?? 0) || s.selectedVersion,
        preset: (e.preset as 'preview' | 'final') ?? s.preset,
      };
    }
    case 'error':
      return { ...s, error: String(e.message ?? 'error') };
    case 'done':
      return {
        ...s,
        render:
          s.render && !s.render.finished && !s.render.endedAt
            ? { ...s.render, endedAt: Date.now() }
            : s.render,
        status: String(e.status ?? s.status),
        costUsd: num(e.total_cost_usd, s.costUsd),
        canRetry: Boolean(e.can_retry),
        pending: String(e.status).startsWith('awaiting') ? s.pending : null,
      };
    default:
      return s;
  }
};

export const reducer = (s: State, a: Action): State => {
  switch (a.type) {
    case 'loaded': {
      const snap = a.snapshot;
      let nextId = 1;
      const messages: Message[] = snap.messages.map((m) => ({
        id: nextId++,
        role: m.role,
        text: m.text,
        card: m.card ?? null,
      }));
      const sel = latest(snap.versions);
      const v = snap.versions.find((x) => x.version === sel);
      return {
        ...initialState,
        projectId: snap.project.id,
        messages,
        nextId,
        status: snap.status,
        pending: snap.pending,
        versions: snap.versions,
        selectedVersion: sel,
        preset: v?.final ? 'final' : 'preview',
        costUsd: snap.cost_usd,
        canRetry: Boolean(snap.can_retry),
        spec: snap.spec,
      };
    }
    case 'user_message':
      return {
        ...s,
        messages: [...s.messages, { id: s.nextId, role: 'user', text: a.text }],
        nextId: s.nextId + 1,
        pending: null,
        error: null,
        canRetry: false,
      };
    case 'system_message':
      return {
        ...s,
        messages: [...s.messages, { id: s.nextId, role: 'system', text: a.text, card: a.card ?? null }],
        nextId: s.nextId + 1,
      };
    case 'busy':
      return { ...s, busy: a.busy };
    case 'server':
      return onServer(s, a.event);
    case 'select_version':
      return { ...s, selectedVersion: a.version };
    case 'select_preset':
      return { ...s, preset: a.preset };
    case 'versions': {
      const sel = latest(a.versions);
      return {
        ...s,
        versions: a.versions,
        selectedVersion: sel ?? s.selectedVersion,
        spec: a.spec === undefined ? s.spec : a.spec,
      };
    }
    case 'error':
      return { ...s, error: a.message, busy: false };
  }
};
