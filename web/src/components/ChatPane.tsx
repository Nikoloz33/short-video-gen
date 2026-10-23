import { useEffect, useRef, useState } from 'react';
import type { Message } from '../reducer';
import { CardView } from './Cards';

export type QuickReply = { label: string; action: 'approve' | 'regenerate' | 'edit'; text?: string };

export const quickReplies = (
  pending: { kind: 'script' | 'video' } | null,
  lang: string | null,
): QuickReply[] => {
  if (!pending) return [];
  const other = lang === 'ka' ? 'English' : 'Georgian';
  if (pending.kind === 'script') {
    return [
      { label: 'Approve script', action: 'approve' },
      { label: 'Shorten', action: 'edit', text: 'Make the video shorter.' },
      { label: `Switch to ${other}`, action: 'edit', text: `Switch the video to ${other}.` },
      { label: 'Regenerate', action: 'regenerate' },
    ];
  }
  return [
    { label: 'Approve final video', action: 'approve' },
    { label: 'Shorten', action: 'edit', text: 'Make the video shorter.' },
    { label: `Switch to ${other}`, action: 'edit', text: `Switch the video to ${other}.` },
    { label: 'Regenerate script', action: 'regenerate' },
  ];
};

type Props = {
  messages: Message[];
  busy: boolean;
  status: string;
  error: string | null;
  replies: QuickReply[];
  projects: { id: string; title: string }[];
  projectId: string | null;
  onSend: (text: string) => void;
  onReply: (r: QuickReply) => void;
  onUpload: (f: File) => void;
  onSelectProject: (id: string) => void;
  onNewProject: () => void;
};

export const ChatPane = (p: Props) => {
  const [text, setText] = useState('');
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [p.messages]);

  const send = () => {
    const t = text.trim();
    if (!t || p.busy) return;
    p.onSend(t);
    setText('');
  };

  return (
    <section className="pane chat" aria-label="Chat">
      <header className="chat-head">
        <strong>InstructVid</strong>
        <select
          aria-label="Project"
          value={p.projectId ?? ''}
          onChange={(e) => p.onSelectProject(e.target.value)}
        >
          {p.projects.map((x) => (
            <option key={x.id} value={x.id}>
              {x.title}
            </option>
          ))}
        </select>
        <button type="button" onClick={p.onNewProject}>
          New
        </button>
        <span className={`status s-${p.status}`}>{p.busy ? 'working…' : p.status.replace(/_/g, ' ')}</span>
      </header>

      <div className="messages">
        {p.messages.length === 0 ? (
          <div className="muted empty">
            Upload a source document (PDF, DOCX, TXT or MD), then describe the video — e.g. “a 45-second
            Georgian training video with one quiz”.
          </div>
        ) : null}
        {p.messages.map((m) => (
          <div key={m.id} className={`msg ${m.role}`}>
            {m.text ? <div className="bubble">{m.text}</div> : null}
            {m.card ? <CardView card={m.card} /> : null}
          </div>
        ))}
        {p.error ? (
          <div className="msg system">
            <div className="bubble err">{p.error}</div>
          </div>
        ) : null}
        <div ref={endRef} />
      </div>

      {p.replies.length ? (
        <div className="replies" role="group" aria-label="Quick replies">
          {p.replies.map((r) => (
            <button key={r.label} type="button" disabled={p.busy} onClick={() => p.onReply(r)}>
              {r.label}
            </button>
          ))}
        </div>
      ) : null}

      <div className="composer">
        <button
          type="button"
          title="Upload source"
          aria-label="Upload source"
          disabled={p.busy || !p.projectId}
          onClick={() => fileRef.current?.click()}
        >
          📎
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.docx,.txt,.md"
          hidden
          data-testid="file-input"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) p.onUpload(f);
            e.target.value = '';
          }}
        />
        <textarea
          aria-label="Message"
          value={text}
          placeholder="Describe the video or ask for a change…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button type="button" className="primary" disabled={p.busy || !text.trim()} onClick={send}>
          Send
        </button>
      </div>
    </section>
  );
};
