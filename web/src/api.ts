/** API client: JSON calls + Server-Sent Events over POST (fetch streaming, EventSource is GET-only). */

export type ServerEvent = { type: string; [k: string]: unknown };

const params = new URLSearchParams(window.location.search);
export const TOKEN: string =
  params.get('token') ?? (import.meta.env.VITE_APP_TOKEN as string | undefined) ?? 'dev-token';

const headers = (json = true): HeadersInit => ({
  Authorization: `Bearer ${TOKEN}`,
  ...(json ? { 'Content-Type': 'application/json' } : {}),
});

const check = async (r: Response) => {
  if (!r.ok) {
    let detail = r.statusText;
    try {
      detail = ((await r.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* not json */
    }
    throw new Error(`${r.status}: ${detail}`);
  }
  return r;
};

export const api = {
  listProjects: async (): Promise<{ id: string; title: string }[]> =>
    (await check(await fetch('/api/projects', { headers: headers() }))).json(),
  createProject: async (title: string): Promise<{ id: string }> =>
    (
      await check(
        await fetch('/api/projects', { method: 'POST', headers: headers(), body: JSON.stringify({ title }) }),
      )
    ).json(),
  snapshot: async (id: string): Promise<Snapshot> =>
    (await check(await fetch(`/api/projects/${id}`, { headers: headers() }))).json(),
  upload: async (id: string, file: File): Promise<UploadResult> => {
    const body = new FormData();
    body.append('file', file);
    return (
      await check(
        await fetch(`/api/projects/${id}/sources`, { method: 'POST', headers: headers(false), body }),
      )
    ).json();
  },
  fileUrl: (id: string, version: number, preset: string, kind: string) =>
    `/api/projects/${id}/versions/${version}/${preset}/${kind}?token=${encodeURIComponent(TOKEN)}`,
};

export type UploadResult = {
  doc_id: string;
  title: string;
  lang: string;
  chars: number;
  redactions: { kind: string; preview: string }[];
  removed_lines: string[];
};

export type VersionInfo = {
  version: number;
  preview: Record<string, boolean> | null;
  final: Record<string, boolean> | null;
};

export type Snapshot = {
  project: { id: string; title: string };
  status: string;
  messages: { role: 'user' | 'agent'; text: string; card?: Card | null }[];
  pending: { kind: 'script' | 'video'; version?: number } | null;
  can_retry?: boolean;
  spec: SpecOutline | null;
  versions: VersionInfo[];
  sources: { doc_id: string; title: string; lang: string; redactions: { kind: string; preview: string }[] }[];
  cost_usd: number;
};

export type SceneOutline = {
  id: string;
  template: string;
  texts: string[];
  narration: string;
  duration_s?: number;
};
export type SpecOutline = {
  version: number;
  title: string;
  lang: string;
  total_s: number;
  scenes: SceneOutline[];
};

export type Card = { kind: string; [k: string]: unknown };

/** Parses an SSE byte stream into events (exported for tests). */
export const parseSSE = (buffer: string): { events: ServerEvent[]; rest: string } => {
  const events: ServerEvent[] = [];
  const blocks = buffer.replace(/\r\n/g, '\n').split('\n\n');
  const rest = blocks.pop() ?? '';
  for (const block of blocks) {
    let data = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('data:')) data += line.slice(5).trimStart();
    }
    if (!data) continue;
    try {
      events.push(JSON.parse(data) as ServerEvent);
    } catch {
      /* ignore malformed */
    }
  }
  return { events, rest };
};

/** POSTs JSON and calls `onEvent` for every server event until the stream ends. */
export const stream = async (
  url: string,
  body: unknown,
  onEvent: (e: ServerEvent) => void,
): Promise<void> => {
  const r = await check(await fetch(url, { method: 'POST', headers: headers(), body: JSON.stringify(body) }));
  const reader = r.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = parseSSE(buffer);
    buffer = rest;
    events.forEach(onEvent);
  }
  parseSSE(buffer + '\n\n').events.forEach(onEvent);
};
