import { useEffect, useRef, useState, type DragEvent } from 'react';
import { statusLabel, WORKING } from '../labels';
import type { Message } from '../reducer';
import { CardView } from './Cards';

export type QuickReply = {
  label: string;
  action: 'approve' | 'regenerate' | 'edit' | 'retry';
  text?: string;
};

export const quickReplies = (
  pending: { kind: 'script' | 'video' } | null,
  lang: string | null,
  canRetry = false,
): QuickReply[] => {
  if (!pending) return canRetry ? [{ label: 'Retry', action: 'retry' }] : [];
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

/** Cards that already say what the agent's sentence would say: show only the card. */
const SELF_EXPLAINING = new Set(['fact_check', 'translation', 'done', 'validation']);

const ACCEPT = '.pdf,.docx,.txt,.md';

type Props = {
  messages: Message[];
  busy: boolean;
  status: string;
  error: string | null;
  replies: QuickReply[];
  projectId: string | null;
  onSend: (text: string) => void;
  onReply: (r: QuickReply) => void;
  onUpload: (f: File) => void;
};

export const ChatPane = (p: Props) => {
  const [text, setText] = useState('');
  const [dragging, setDragging] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [p.messages, p.replies.length]);

  const canUpload = !p.busy && Boolean(p.projectId);
  const send = () => {
    const t = text.trim();
    if (!t || p.busy) return;
    p.onSend(t);
    setText('');
  };
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f && canUpload) p.onUpload(f);
  };
  const working = p.busy || WORKING.has(p.status);

  return (
    <section
      className={`pane chat ${dragging ? 'is-dragging' : ''}`}
      aria-label="Chat"
      onDragOver={(e) => {
        e.preventDefault();
        if (canUpload) setDragging(true);
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
    >
      <div className="messages" aria-live="polite">
        {p.messages.length === 0 ? (
          <div className="welcome">
            <h2>Start from the document your team already trusts.</h2>
            <p>
              Upload a procedure, safety instruction or discharge sheet. Then describe the video you need, for
              example “a 45-second Georgian training video with one quiz”. Every sentence in the video is
              checked against your document before you see it.
            </p>
            <button
              type="button"
              className="drop"
              disabled={!canUpload}
              onClick={() => fileRef.current?.click()}
            >
              <span className="doc-glyph" aria-hidden="true" />
              <span>
                <strong>Choose a document</strong> or drop it here
                <small>PDF, Word, plain text or Markdown</small>
              </span>
            </button>
          </div>
        ) : null}
        {p.messages.map((m) => (
          <article key={m.id} className={`msg from-${m.role}`}>
            {m.text && !SELF_EXPLAINING.has(String(m.card?.kind)) ? (
              <p className="msg-text">{m.text}</p>
            ) : null}
            {m.card ? <CardView card={m.card} /> : null}
          </article>
        ))}
        {p.error ? (
          <p className="alert" role="alert">
            {p.error}
          </p>
        ) : null}
        {working ? (
          <p className="working" role="status">
            <span className="pulse" aria-hidden="true" />
            {statusLabel(p.status)}
          </p>
        ) : null}
        <div ref={endRef} />
      </div>

      {p.replies.length ? (
        <div className="replies" role="group" aria-label="Quick replies">
          {p.replies.map((r, i) => (
            <button
              key={r.label}
              type="button"
              className={i === 0 ? 'btn primary' : 'btn'}
              disabled={p.busy}
              onClick={() => p.onReply(r)}
            >
              {r.label}
            </button>
          ))}
        </div>
      ) : null}

      <form
        className="composer"
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
      >
        <button
          type="button"
          className="btn icon"
          title="Upload a source document"
          aria-label="Upload source"
          disabled={!canUpload}
          onClick={() => fileRef.current?.click()}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M12 18v-6M9 15l3-3 3 3"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
        <input
          ref={fileRef}
          type="file"
          accept={ACCEPT}
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
          rows={2}
          placeholder="Describe the video, or ask for a change"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
        />
        <button type="submit" className="btn primary" disabled={p.busy || !text.trim()}>
          Send
        </button>
      </form>
    </section>
  );
};
