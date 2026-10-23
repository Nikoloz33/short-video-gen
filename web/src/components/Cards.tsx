/** Inline chat cards: plan, script, fact-check, translation, edits, redactions, results. */
import type { Card } from '../api';

type Claim = {
  text: string;
  verdict: string;
  why: string;
  gate?: string | null;
  quote?: string | null;
  chunk_id?: string | null;
  source?: string | null;
};
type FactScene = { scene_id: string; ok: boolean; claims: Claim[]; translation_problems: string[] };

const Verdict = ({ v }: { v: string }) => <span className={`verdict v-${v}`}>{v.replace('_', ' ')}</span>;

const FactCheck = ({ card }: { card: Card }) => {
  const scenes = (card.scenes as FactScene[]) ?? [];
  const counts = (card.counts as Record<string, number>) ?? {};
  const failing = scenes.filter((s) => !s.ok);
  return (
    <div className={`card ${card.ok ? 'ok' : 'bad'}`}>
      <div className="card-title">
        Fact-check {card.ok ? '✓' : '⚠'}{' '}
        <span className="muted">
          {Object.entries(counts)
            .map(([k, n]) => `${n} ${k.replace('_', ' ')}`)
            .join(' · ')}
        </span>
      </div>
      {failing.length === 0 ? (
        <div className="muted">Every claim is supported by the source.</div>
      ) : (
        failing.map((s) => (
          <div key={s.scene_id} className="fact-scene">
            <div className="scene-id">Scene {s.scene_id}</div>
            {s.claims
              .filter((c) => c.verdict !== 'supported')
              .map((c, i) => (
                <div key={i} className="claim">
                  <div>
                    <Verdict v={c.verdict} /> {c.text}
                  </div>
                  <div className="why">
                    Why: {c.why}
                    {c.gate ? ` (${c.gate} check)` : ''}
                  </div>
                  {c.quote || c.source ? (
                    <blockquote title={c.chunk_id ?? ''}>{c.quote || c.source}</blockquote>
                  ) : null}
                </div>
              ))}
            {s.translation_problems.map((p, i) => (
              <div key={`t${i}`} className="claim">
                <Verdict v="translation" /> {p}
              </div>
            ))}
          </div>
        ))
      )}
      <details>
        <summary>All scenes</summary>
        {scenes.map((s) => (
          <div key={s.scene_id} className="fact-scene">
            <div className="scene-id">
              {s.scene_id} {s.ok ? '✓' : '⚠'}
            </div>
            {s.claims.map((c, i) => (
              <div key={i} className="claim small">
                <Verdict v={c.verdict} /> {c.text}
                {c.quote ? <blockquote>{c.quote}</blockquote> : null}
              </div>
            ))}
          </div>
        ))}
      </details>
    </div>
  );
};

type ScriptScene = { id: string; template: string; texts: string[]; narration: string; icon?: string | null };

const Script = ({ card }: { card: Card }) => (
  <div className="card">
    <div className="card-title">
      Script v{String(card.version)} · {String(card.lang).toUpperCase()} · ~{String(card.estimated_s)} s
    </div>
    <ol className="script">
      {((card.scenes as ScriptScene[]) ?? []).map((s) => (
        <li key={s.id}>
          <span className="tpl">{s.template.replace('_', ' ')}</span> {s.texts.join(' · ').replace(/\*/g, '')}
          <div className="narration">🔊 {s.narration}</div>
        </li>
      ))}
    </ol>
  </div>
);

const Plan = ({ card }: { card: Card }) => (
  <div className="card">
    <div className="card-title">
      Plan · {String(card.target_sec)} s · {String(card.language).toUpperCase()}
    </div>
    <div>{String(card.goal)}</div>
    <ol>
      {((card.steps as string[]) ?? []).map((s, i) => (
        <li key={i}>{s}</li>
      ))}
    </ol>
    {((card.quiz_topics as string[]) ?? []).length ? (
      <div className="muted">Quiz: {(card.quiz_topics as string[]).join('; ')}</div>
    ) : null}
  </div>
);

const Redactions = ({ card }: { card: Card }) => {
  const r = (card.redactions as { kind: string; preview: string }[]) ?? [];
  const removed = (card.removed_lines as string[]) ?? [];
  return (
    <div className="card">
      <div className="card-title">
        Source uploaded: {String(card.title)} ({String(card.lang).toUpperCase()})
      </div>
      {r.length ? (
        <div>
          Redacted before anything left this machine:{' '}
          {r.map((x, i) => (
            <span key={i} className="chip">
              {x.kind}: {x.preview}
            </span>
          ))}
        </div>
      ) : (
        <div className="muted">No personal data found.</div>
      )}
      {removed.length ? (
        <div className="muted">Ignored {removed.length} line(s) that looked like instructions.</div>
      ) : null}
    </div>
  );
};

const Done = ({ card }: { card: Card }) => (
  <div className="card ok">
    <div className="card-title">Final video v{String(card.version)} ready</div>
    <div className="muted">Model cost ${Number(card.cost_usd ?? 0).toFixed(3)}</div>
  </div>
);

const Generic = ({ card }: { card: Card }) => {
  const k = card.kind;
  if (k === 'translation') {
    const problems = (card.problems as Record<string, string[]>) ?? {};
    const n = Object.keys(problems).length;
    return (
      <div className={`card ${n ? 'bad' : 'ok'}`}>
        <div className="card-title">Translation → {String(card.to).toUpperCase()}</div>
        {n ? (
          Object.entries(problems).map(([sid, p]) => (
            <div key={sid}>
              {sid}: {p.join('; ')}
            </div>
          ))
        ) : (
          <div className="muted">Numbers, names and negations preserved.</div>
        )}
      </div>
    );
  }
  if (k === 'edit') {
    return (
      <div className="card">
        <div className="card-title">Edit → v{String(card.version)}</div>
        {((card.ops as Record<string, unknown>[]) ?? []).map((o, i) => (
          <code key={i} className="op">
            {Object.entries(o)
              .map(([a, b]) => `${a}=${String(b)}`)
              .join(' ')}
          </code>
        ))}
      </div>
    );
  }
  if (k === 'layout' || k === 'validation') {
    const items =
      ((card.issues ?? card.checks) as {
        message?: string;
        name?: string;
        detail?: string;
        ok?: boolean;
      }[]) ?? [];
    return (
      <div className="card bad">
        <div className="card-title">{k === 'layout' ? 'Layout check' : 'Video validation'}</div>
        {items
          .filter((i) => i.ok !== true)
          .map((i, n) => (
            <div key={n}>{i.message ?? `${i.name}: ${i.detail}`}</div>
          ))}
      </div>
    );
  }
  if (k === 'video') return null;
  if (k === 'source' || k === 'fix')
    return (
      <div className="card muted">
        {String(card.note ?? `${String(card.new_chunks ?? '')} passages indexed`)}
      </div>
    );
  return null;
};

export const CardView = ({ card }: { card: Card }) => {
  switch (card.kind) {
    case 'fact_check':
      return <FactCheck card={card} />;
    case 'script':
      return <Script card={card} />;
    case 'plan':
      return <Plan card={card} />;
    case 'upload':
      return <Redactions card={card} />;
    case 'done':
      return <Done card={card} />;
    default:
      return <Generic card={card} />;
  }
};
