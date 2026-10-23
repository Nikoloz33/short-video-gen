import { api, type VersionInfo } from '../api';
import type { RenderState } from '../reducer';
import { computeSpeed, fmtMs, fmtS } from '../speed';

const STAGES: [string, string][] = [
  ['tts', 'TTS'],
  ['bundle_ms', 'bundle'],
  ['render_ms', 'render'],
  ['encode_ms', 'encode'],
];

export const SpeedPanel = ({ r, now }: { r: RenderState | null; now: number }) => {
  if (!r) return <div className="speed muted">No render yet.</div>;
  const fps = r.preset === 'final' ? 30 : 15;
  const sp = computeSpeed({ ...r, fps });
  const elapsed = r.finished ? r.elapsedMs / 1000 : Math.max(0, now - r.startedAt) / 1000;
  const ttsMs = r.tts.ms;
  return (
    <div className="speed" aria-label="Render speed">
      <div className="speed-row">
        <span className="stage">{r.finished ? 'done' : r.stage}</span>
        <span>
          {r.preset} v{r.version ?? '—'}
        </span>
      </div>
      <div className="bar">
        <div style={{ width: `${Math.round((r.finished ? 1 : sp.fraction) * 100)}%` }} />
      </div>
      <div className="speed-grid">
        <div>
          frames{' '}
          <b>
            {r.renderedFrames}/{r.totalFrames || '—'}
          </b>
        </div>
        <div>
          <b>{sp.renderFps.toFixed(0)}</b> fps
        </div>
        <div>
          <b>{sp.realtime.toFixed(2)}×</b> realtime
        </div>
        <div>ETA {r.finished ? '0:00' : fmtS(sp.etaS)}</div>
        <div>elapsed {fmtS(elapsed)}</div>
        <div>
          cache {r.tts.cache_hits ?? 0} TTS hit{(r.tts.cache_hits ?? 0) === 1 ? '' : 's'}
          {r.bundleCacheHit ? ' · bundle hit' : ''}
        </div>
      </div>
      <div className="stages">
        {STAGES.map(([k, label]) => {
          const ms = k === 'tts' ? ttsMs : r.stages[k];
          const active =
            !r.finished && (r.stage === k.replace('_ms', '') || (k === 'tts' && r.stage === 'tts'));
          return (
            <span key={k} className={active ? 'active' : ms !== undefined ? 'done' : ''}>
              {label} {ms !== undefined ? fmtMs(ms) : active ? '…' : '—'}{' '}
              {ms !== undefined && !active ? '✓' : ''}
            </span>
          );
        })}
      </div>
    </div>
  );
};

type Props = {
  projectId: string | null;
  versions: VersionInfo[];
  selected: number | null;
  preset: 'preview' | 'final';
  render: RenderState | null;
  now: number;
  onVersion: (v: number) => void;
  onPreset: (p: 'preview' | 'final') => void;
};

export const VideoPane = (p: Props) => {
  const v = p.versions.find((x) => x.version === p.selected);
  const files = v ? v[p.preset] : null;
  const url = (kind: string) =>
    p.projectId && p.selected ? api.fileUrl(p.projectId, p.selected, p.preset, kind) : '';
  return (
    <section className="pane video" aria-label="Video">
      <div className="video-head">
        <label>
          version{' '}
          <select
            aria-label="Version"
            value={p.selected ?? ''}
            onChange={(e) => p.onVersion(Number(e.target.value))}
          >
            {p.versions
              .filter((x) => x.preview || x.final)
              .map((x) => (
                <option key={x.version} value={x.version}>
                  v{x.version}
                </option>
              ))}
          </select>
        </label>
        <div className="toggle" role="radiogroup" aria-label="Preset">
          {(['preview', 'final'] as const).map((k) => (
            <label key={k} className={!v?.[k] ? 'disabled' : ''}>
              <input
                type="radio"
                name="preset"
                checked={p.preset === k}
                disabled={!v?.[k]}
                onChange={() => p.onPreset(k)}
              />{' '}
              {k}
            </label>
          ))}
        </div>
      </div>
      <div className="player">
        {files?.mp4 ? (
          <video key={url('mp4')} controls src={url('mp4')} data-testid="player">
            {files.vtt ? <track kind="captions" src={url('vtt')} default /> : null}
          </video>
        ) : (
          <div className="placeholder muted">The video appears here after the first preview render.</div>
        )}
      </div>
      <SpeedPanel r={p.render} now={p.now} />
      <div className="downloads">
        <a className={files?.mp4 ? '' : 'disabled'} href={files?.mp4 ? url('mp4') : undefined} download>
          Download MP4
        </a>
        <a className={files?.srt ? '' : 'disabled'} href={files?.srt ? url('srt') : undefined} download>
          SRT
        </a>
        <a className={files?.quiz ? '' : 'disabled'} href={files?.quiz ? url('quiz') : undefined} download>
          quiz.json
        </a>
      </div>
    </section>
  );
};
