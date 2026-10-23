import { useCallback, useEffect, useReducer, useState } from 'react';
import { api, stream, type ServerEvent } from './api';
import { ChatPane, quickReplies, type QuickReply } from './components/ChatPane';
import { VideoPane } from './components/VideoPane';
import { initialState, reducer } from './reducer';

export const App = () => {
  const [state, dispatch] = useReducer(reducer, initialState);
  const [projects, setProjects] = useState<{ id: string; title: string }[]>([]);
  const [lang, setLang] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async (id: string) => {
    const snap = await api.snapshot(id);
    dispatch({ type: 'loaded', snapshot: snap });
    setLang(snap.spec?.lang ?? null);
  }, []);

  const refresh = useCallback(async () => {
    if (!state.projectId) return;
    const snap = await api.snapshot(state.projectId);
    dispatch({ type: 'versions', versions: snap.versions });
    setLang(snap.spec?.lang ?? null);
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
        dispatch({ type: 'error', message: String(e) });
      }
    })();
  }, [load]);

  // Keep elapsed / ETA moving while a render is running.
  useEffect(() => {
    if (!state.render || state.render.finished) return;
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
    void run(`/api/projects/${pid}/resume`, { action: r.action, text: r.text });
  };

  const onUpload = async (f: File) => {
    if (!pid) return;
    dispatch({ type: 'busy', busy: true });
    try {
      const res = await api.upload(pid, f);
      dispatch({ type: 'system_message', text: '', card: { kind: 'upload', ...res } });
    } catch (e) {
      dispatch({ type: 'error', message: String(e) });
    } finally {
      dispatch({ type: 'busy', busy: false });
    }
  };

  const onNewProject = async () => {
    const title = window.prompt('Project name', 'New video') ?? 'New video';
    const { id } = await api.createProject(title);
    setProjects(await api.listProjects());
    await load(id);
  };

  return (
    <div className="app">
      <ChatPane
        messages={state.messages}
        busy={state.busy}
        status={state.status}
        error={state.error}
        replies={state.busy ? [] : quickReplies(state.pending, lang)}
        projects={projects}
        projectId={pid}
        onSend={onSend}
        onReply={onReply}
        onUpload={onUpload}
        onSelectProject={(id) => void load(id)}
        onNewProject={() => void onNewProject()}
      />
      <VideoPane
        projectId={pid}
        versions={state.versions}
        selected={state.selectedVersion}
        preset={state.preset}
        render={state.render}
        now={now}
        onVersion={(v) => dispatch({ type: 'select_version', version: v })}
        onPreset={(p) => dispatch({ type: 'select_preset', preset: p })}
      />
    </div>
  );
};
