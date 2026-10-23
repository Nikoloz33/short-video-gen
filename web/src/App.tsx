import { useCallback, useEffect, useMemo, useReducer, useState } from 'react';
import { api, stream, type ServerEvent } from './api';
import { ChatPane, quickReplies, type QuickReply } from './components/ChatPane';
import { markOf, type MarkKind } from './components/Mark';
import { VideoPane } from './components/VideoPane';
import { statusLabel, WORKING } from './labels';
import { initialState, reducer, type Message } from './reducer';

/** Verification mark per scene from the latest fact-check card in the conversation. */
export const sceneMarks = (messages: Message[]): Record<string, MarkKind> => {
  for (let i = messages.length - 1; i >= 0; i--) {
    const card = messages[i]!.card;
    if (card?.kind !== 'fact_check') continue;
    const out: Record<string, MarkKind> = {};
    for (const s of (card.scenes as { scene_id: string; ok: boolean; claims: { verdict: string }[] }[]) ??
      []) {
      const worst = s.claims.map((c) => markOf(c.verdict));
      out[s.scene_id] = s.ok ? 'ok' : worst.includes('bad') ? 'bad' : 'partial';
    }
    return out;
  }
  return {};
};

/** Claims of the latest fact-check still waiting for the reviewer's decision. */
export const flaggedCount = (messages: Message[]): number => {
  for (let i = messages.length - 1; i >= 0; i--) {
    const card = messages[i]!.card;
    if (card?.kind === 'fact_check') return Number(card.flagged ?? 0);
  }
  return 0;
};

export const App = () => {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [projects, setProjects] = useState<{ id: string; title: string }[]>([]);
  const [now, setNow] = useState(() => Date.now());
  const lang = state.spec?.lang ?? null;

  const load = useCallback(async (id: string) => {
    dispatch({ type: 'loaded', snapshot: await api.snapshot(id) });
  }, []);

  const refresh = useCallback(async () => {
    if (!state.projectId) return;
    const snap = await api.snapshot(state.projectId);
    dispatch({ type: 'versions', versions: snap.versions, spec: snap.spec });
  }, [state.projectId]);

  useEffect(() => {
    (async () => {
      try {
        let list = await api.listProjects();
        if (!list.length) {
          await api.createProject('My first video');
          list = await api.listProjects();
        }
        setProjects(list);
        await load(list[0]!.id);
      } catch (e) {
        dispatch({ type: 'error', message: `Could not reach the server: ${String(e)}` });
      }
    })();
  }, [load]);

  // Keep elapsed time and ETA moving while a render is running.
  useEffect(() => {
    if (!state.render || state.render.finished || state.render.endedAt) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [state.render]);

  const run = async (url: string, body: unknown) => {
    dispatch({ type: 'busy', busy: true });
    try {
      await stream(url, body, (event: ServerEvent) => dispatch({ type: 'server', event }));
    } catch (e) {
      dispatch({ type: 'error', message: String(e) });
    } finally {
      dispatch({ type: 'busy', busy: false });
      await refresh();
    }
  };

  const pid = state.projectId;

  const onSend = (text: string) => {
    if (!pid) return;
    dispatch({ type: 'user_message', text });
    void run(`/api/projects/${pid}/messages`, { text });
  };

  const onReply = (r: QuickReply) => {
    if (!pid) return;
    dispatch({ type: 'user_message', text: r.text ?? r.label });
    if (r.action === 'retry') void run(`/api/projects/${pid}/retry`, {});
    else
      void run(`/api/projects/${pid}/resume`, {
        action: r.action,
        text: r.text,
        scene_id: r.scene_id,
        index: r.index,
      });
  };

  const onUpload = async (f: File) => {
    if (!pid) return;
    dispatch({ type: 'busy', busy: true });
    try {
      const res = await api.upload(pid, f);
      dispatch({ type: 'system_message', text: '', card: { kind: 'upload', ...res } });
    } catch (e) {
      dispatch({ type: 'error', message: `The document was not uploaded: ${String(e)}` });
    } finally {
      dispatch({ type: 'busy', busy: false });
    }
  };

  const onNewProject = async () => {
    const { id } = await api.createProject(`New video ${projects.length + 1}`);
    setProjects(await api.listProjects());
    await load(id);
  };

  const marks = useMemo(() => sceneMarks(state.messages), [state.messages]);
  // A run that stopped mid-way keeps its last status: say so instead of pretending to work.
  const stopped = !state.busy && state.canRetry;
  const working = state.busy || (!stopped && WORKING.has(state.status));

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            <Logo />
          </span>
          <span className="brand-name">InstructVid</span>
        </div>
        <label className="field project">
          <span className="visually-hidden">Project</span>
          <select aria-label="Project" value={pid ?? ''} onChange={(e) => void load(e.target.value)}>
            {projects.map((x) => (
              <option key={x.id} value={x.id}>
                {x.title}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn" onClick={() => void onNewProject()}>
          New video
        </button>
        <p className={`status ${working ? 'is-working' : ''}`} aria-live="polite">
          {stopped ? 'Stopped — press Retry to continue' : statusLabel(state.status)}
          {state.costUsd ? <span className="cost">${state.costUsd.toFixed(2)} used</span> : null}
        </p>
      </header>
      <main className="app">
        <ChatPane
          messages={state.messages}
          busy={state.busy}
          status={state.status}
          error={state.error}
          replies={
            state.busy ? [] : quickReplies(state.pending, lang, state.canRetry, flaggedCount(state.messages))
          }
          onDecide={state.pending?.kind === 'script' ? onReply : undefined}
          projectId={pid}
          onSend={onSend}
          onReply={onReply}
          onUpload={onUpload}
        />
        <VideoPane
          projectId={pid}
          versions={state.versions}
          selected={state.selectedVersion}
          preset={state.preset}
          render={state.render}
          now={now}
          spec={state.spec}
          marks={marks}
          onVersion={(v) => dispatch({ type: 'select_version', version: v })}
          onPreset={(p) => dispatch({ type: 'select_preset', preset: p })}
        />
      </main>
    </div>
  );
};

/** A 9:16 frame holding a check — the product in one glyph. */
const Logo = () => (
  <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
    <rect x="5" y="1.5" width="12" height="19" rx="2.5" fill="none" stroke="currentColor" strokeWidth="1.8" />
    <path
      d="M8 11.3 10.2 13.4 14 8.8"
      fill="none"
      stroke="var(--safe)"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);
