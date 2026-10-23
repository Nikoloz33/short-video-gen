/** Inline chat cards. Each kind has its own shape: a ledger for facts, a sequence for the plan,
 * a storyboard for the script — not one generic box. */
import type { Card } from '../api';
import type { QuickReply } from './ChatPane';
import { GATE, TEMPLATE, VERDICT } from '../labels';
import { Mark, markOf } from './Mark';

type Claim = {
  text: string;
  verdict: string;
  why: string;
  gate?: string | null;
  quote?: string | null;
  chunk_id?: string | null;
  source?: string | null;
  index?: number;
  confirmed_by?: string | null;
};
type Decide = (r: QuickReply) => void;
type FactScene = { scene_id: string; ok: boolean; claims: Claim[]; translation_problems: string[] };

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

const ClaimRow = ({ c, sceneId, onDecide }: { c: Claim; sceneId?: string; onDecide?: Decide }) => (
  <li className="claim">
    <Mark kind={c.confirmed_by ? 'ok' : markOf(c.verdict)} />
    <div>
      <p className="claim-text">{c.text}</p>
      {c.verdict !== 'supported' ? (
        <p className="claim-why">
          {VERDICT[c.verdict] ?? c.verdict}
          {c.gate ? ` (${GATE[c.gate] ?? c.gate})` : ''}: {c.why}
        </p>
      ) : null}
      {c.quote || c.source ? (
        <blockquote className="source-quote" title={c.chunk_id ? `Source passage ${c.chunk_id}` : undefined}>
          {c.quote || c.source}
        </blockquote>
      ) : null}
      {c.confirmed_by ? <p className="claim-kept">Kept by {c.confirmed_by}</p> : null}
      {onDecide && sceneId && !c.confirmed_by && c.verdict !== 'supported' ? (
        <div className="claim-actions" role="group" aria-label="Decide this claim">
          <button
            type="button"
            className="btn small"
            onClick={() =>
              onDecide({ label: `Keep: ${c.text}`, action: 'keep_claim', scene_id: sceneId, index: c.index })
            }
          >
            Keep
          </button>
          <button
            type="button"
            className="btn small"
            onClick={() =>
              onDecide({
                label: `Remove: ${c.text}`,
                action: 'remove_claim',
                scene_id: sceneId,
                index: c.index,
              })
            }
          >
            Remove
          </button>
        </div>
      ) : null}
    </div>
  </li>
);

const FactLedger = ({ card, onDecide }: { card: Card; onDecide?: Decide }) => {
  const scenes = (card.scenes as FactScene[]) ?? [];
  const counts = (card.counts as Record<string, number>) ?? {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  const ok = counts.supported ?? 0;
  const failing = scenes.filter((s) => !s.ok);
  return (
    <section className={`card ledger ${card.ok ? 'is-ok' : 'is-bad'}`} aria-label="Fact-check">
      <header className="card-head">
        <Mark kind={card.ok ? 'ok' : 'bad'} size={18} />
        <h3>
          {card.ok
            ? `All ${total} claims are in your document`
            : `${total - ok} of ${total} claims need a look`}
        </h3>
      </header>
      <div className="tally" aria-hidden="true">
        {(['supported', 'partially_supported', 'unsupported', 'contradicts'] as const).map((k) =>
          counts[k] ? (
            <span key={k} className={`tally-${markOf(k)}`} style={{ flexGrow: counts[k] }} />
          ) : null,
        )}
      </div>
      {failing.map((s) => (
        <div key={s.scene_id} className="ledger-scene">
          <h4>Scene {s.scene_id.replace(/^s/, '')}</h4>
          <ul>
            {s.claims
              .filter((c) => c.verdict !== 'supported')
              .map((c, i) => (
                <ClaimRow key={i} c={c} sceneId={s.scene_id} onDecide={onDecide} />
              ))}
            {s.translation_problems.map((p, i) => (
              <li key={`t${i}`} className="claim">
                <Mark kind="partial" />
                <p className="claim-text">Translation: {p}</p>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <details className="more">
        <summary>Show all {plural(total, 'claim')} with their sources</summary>
        {scenes.map((s) => (
          <div key={s.scene_id} className="ledger-scene">
            <h4>Scene {s.scene_id.replace(/^s/, '')}</h4>
            <ul>
              {s.claims.map((c, i) => (
                <ClaimRow key={i} c={c} />
              ))}
            </ul>
          </div>
        ))}
      </details>
    </section>
  );
};

type ScriptScene = { id: string; template: string; texts: string[]; narration: string };

const Storyboard = ({ card }: { card: Card }) => {
  const scenes = (card.scenes as ScriptScene[]) ?? [];
  return (
    <section className="card storyboard" aria-label="Script">
      <header className="card-head">
        <h3>
          Script, version {String(card.version)}
          <span className="sub">
            {String(card.lang) === 'ka' ? 'Georgian' : 'English'}, about {String(card.estimated_s)} seconds,{' '}
            {plural(scenes.length, 'scene')}
          </span>
        </h3>
      </header>
      <p className="aside">
        Each scene appears in the scene list with its fact-check mark. Read the narration before you approve.
      </p>
      <details className="more">
        <summary>Show the full script</summary>
        <ol>
          {scenes.map((s) => (
            <li key={s.id}>
              <span className="tpl">{TEMPLATE[s.template] ?? s.template}</span>
              <p className="onscreen">{s.texts.join(' / ').replace(/\*/g, '')}</p>
              <p className="voice">“{s.narration}”</p>
            </li>
          ))}
        </ol>
      </details>
    </section>
  );
};

const Plan = ({ card }: { card: Card }) => (
  <section className="card plan" aria-label="Plan">
    <header className="card-head">
      <h3>
        Plan
        <span className="sub">
          {String(card.target_sec)} seconds in {String(card.language) === 'ka' ? 'Georgian' : 'English'}
        </span>
      </h3>
    </header>
    <p className="goal">{String(card.goal)}</p>
    <ol className="steps">
      {((card.steps as string[]) ?? []).map((s, i) => (
        <li key={i}>{s}</li>
      ))}
    </ol>
    {((card.quiz_topics as string[]) ?? []).length ? (
      <p className="aside">Quiz: {(card.quiz_topics as string[]).join('; ')}</p>
    ) : null}
  </section>
);

const Upload = ({ card }: { card: Card }) => {
  const r = (card.redactions as { kind: string; preview: string }[]) ?? [];
  const removed = (card.removed_lines as string[]) ?? [];
  return (
    <section className="card upload" aria-label="Uploaded document">
      <header className="card-head">
        <span className="doc-glyph" aria-hidden="true" />
        <h3>
          Source uploaded: {String(card.title)}
          <span className="sub">
            {String(card.lang) === 'ka' ? 'Georgian' : 'English'}, {Number(card.chars ?? 0).toLocaleString()}{' '}
            characters
          </span>
        </h3>
      </header>
      {r.length ? (
        <>
          <p>Removed before anything left this computer:</p>
          <ul className="redactions">
            {r.map((x, i) => (
              <li key={i}>
                <span className="kind">{x.kind}</span> <code>{x.preview}</code>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="aside">No personal data found.</p>
      )}
      {removed.length ? (
        <p className="aside">
          Ignored {plural(removed.length, 'line')} that tried to give the AI instructions.
        </p>
      ) : null}
    </section>
  );
};

const opText = (o: Record<string, unknown>): string => {
  const scene = o.scene_id ? `scene ${String(o.scene_id).replace(/^s(\d+)$/, '$1')}` : 'the video';
  switch (o.op) {
    case 'set_text':
      return `Rewrote the ${String(o.field)} of ${scene}`;
    case 'set_icon':
      return `Changed the icon of ${scene} to “${String(o.icon)}”`;
    case 'reorder':
      return 'Reordered the scenes';
    case 'delete_scene':
      return `Removed ${scene}`;
    case 'add_scene':
      return `Added a ${TEMPLATE[String(o.template)]?.toLowerCase() ?? 'new'} scene`;
    case 'add_quiz':
      return 'Added a quiz question';
    case 'set_language':
      return `Switched the video to ${o.language === 'ka' ? 'Georgian' : 'English'}`;
    case 'set_voice':
      return `Changed the voice to ${String(o.voice)}`;
    case 'set_target_duration':
      return `Set the length to ${String(o.target_sec)} seconds`;
    case 'regenerate_scene':
      return `Rewrote ${scene}${o.instruction ? `: ${String(o.instruction)}` : ''}`;
    default:
      return String(o.op);
  }
};

const Simple = ({ card }: { card: Card }) => {
  switch (card.kind) {
    case 'translation': {
      const problems = (card.problems as Record<string, string[]>) ?? {};
      const n = Object.keys(problems).length;
      return (
        <section className={`card note ${n ? 'is-warn' : ''}`}>
          <Mark kind={n ? 'partial' : 'ok'} />
          <p>
            Translated to {card.to === 'ka' ? 'Georgian' : 'English'}.{' '}
            {n
              ? `${plural(n, 'scene')} changed a number, name or negation and will be corrected.`
              : 'Numbers, names and negations match the original.'}
          </p>
        </section>
      );
    }
    case 'edit':
      return (
        <section className="card note">
          <ul className="ops">
            {((card.ops as Record<string, unknown>[]) ?? []).map((o, i) => (
              <li key={i}>{opText(o)}</li>
            ))}
          </ul>
          <p className="aside">Saved as version {String(card.version)}.</p>
        </section>
      );
    case 'fix':
      return card.note ? (
        <section className="card note">
          <p>{String(card.note)}</p>
        </section>
      ) : null;
    case 'layout':
    case 'validation': {
      const items =
        ((card.issues ?? card.checks) as {
          message?: string;
          name?: string;
          detail?: string;
          ok?: boolean;
        }[]) ?? [];
      return (
        <section className="card note is-bad">
          <Mark kind="bad" />
          <div>
            <p>
              {card.kind === 'layout'
                ? 'Some text does not fit on screen:'
                : 'The video did not pass its checks:'}
            </p>
            <ul>
              {items
                .filter((i) => i.ok !== true)
                .map((i, n) => (
                  <li key={n}>{i.message ?? `${i.name}: ${i.detail}`}</li>
                ))}
            </ul>
          </div>
        </section>
      );
    }
    case 'done':
      return (
        <section className="card note is-ok">
          <Mark kind="ok" />
          <p>
            Final video, version {String(card.version)}, is ready. Model cost for this video: $
            {Number(card.cost_usd ?? 0).toFixed(2)}.
          </p>
        </section>
      );
    default:
      return null; // source / video cards are reflected elsewhere (studio pane)
  }
};

export const CardView = ({ card, onDecide }: { card: Card; onDecide?: Decide }) => {
  switch (card.kind) {
    case 'fact_check':
      return <FactLedger card={card} onDecide={onDecide} />;
    case 'script':
      return <Storyboard card={card} />;
    case 'plan':
      return <Plan card={card} />;
    case 'upload':
      return <Upload card={card} />;
    default:
      return <Simple card={card} />;
  }
};
