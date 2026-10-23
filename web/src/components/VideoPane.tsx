import { useRef } from 'react';
import { api, type SceneOutline, type SpecOutline, type VersionInfo } from '../api';
import { TEMPLATE } from '../labels';
import type { RenderState } from '../reducer';
import { computeSpeed, fmtMs, fmtS } from '../speed';
import { Mark, type MarkKind } from './Mark';

type Stage = { key: string; label: string; ms: number | undefined; state: 'done' | 'active' | 'waiting' };

const stagesOf = (r: RenderState): Stage[] => {
  const order = ['tts', 'bundle', 'render', 'encode'];
  const current = r.finished ? 'done' : r.stage === 'post' || r.stage === 'validate' ? 'encode' : r.stage;
  const at = order.indexOf(current);
  const ms: Record<string, number | undefined> = {
    tts: r.tts.ms,
    bundle: r.stages.bundle_ms,
    render: r.stages.render_ms,
    encode: r.stages.encode_ms,
  };
  const label: Record<string, string> = {
    tts: 'Narration',
    bundle: 'Bundle',
    render: 'Render',
    encode: 'Encode',
  };
  return order.map((key, i) => ({
    key,
    label: label[key]!,
    ms: ms[key],
    state: r.finished || (at >= 0 && i < at) ? 'done' : i === at ? 'active' : 'waiting',
  }));
};

export const SpeedPanel = ({ r, now }: { r: RenderState | null; now: number }) => {
  if (!r)
    return (
      <section className="meter is-idle" aria-label="Render speed">
        <p>Render progress and speed appear here while a video is being made.</p>
      </section>
    );
  const fps = r.preset === 'final' ? 30 : 15;
  const sp = computeSpeed({ ...r, fps });
  const elapsed = r.finished ? r.elapsedMs / 1000 : Math.max(0, (r.endedAt ?? now) - r.startedAt) / 1000;
  const hits = r.tts.cache_hits ?? 0;
  const pct = Math.round((r.finished ? 1 : sp.fraction) * 100);
  return (
    <section className="meter" aria-label="Render speed">
      <ol className="track">
        {stagesOf(r).map((s) => (
          <li key={s.key} className={`stage is-${s.state}`}>
            <span className="stage-name">{s.label}</span>
            <span className="stage-time">
              {s.ms !== undefined ? fmtMs(s.ms) : s.state === 'active' ? 'running' : ''}
            </span>
          </li>
        ))}
      </ol>
      <div className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
        <span style={{ transform: `scaleX(${pct / 100})` }} />
      </div>
      <dl className="readout">
        <div>
          <dt>Frames</dt>
          <dd>
            {r.renderedFrames}/{r.totalFrames || '—'}
          </dd>
        </div>
        <div>
          <dt>Speed</dt>
          <dd>{sp.renderFps.toFixed(0)} fps</dd>
        </div>
        <div>
          <dt>Realtime</dt>
          <dd>{sp.realtime.toFixed(2)}×</dd>
        </div>
        <div>
          <dt>Time left</dt>
          <dd>{r.finished ? '0:00' : fmtS(sp.etaS)}</dd>
        </div>
        <div>
          <dt>Elapsed</dt>
          <dd>{fmtS(elapsed)}</dd>
        </div>
      </dl>
      <p className="meter-note">
        {r.preset === 'final' ? 'Final 1080×1920' : 'Preview 540×960'}, version {r.version ?? '—'}.
        {hits ? ` Reused ${hits} narration ${hits === 1 ? 'clip' : 'clips'} from earlier versions.` : ''}
        {r.bundleCacheHit ? ' Templates were already compiled.' : ''}
      </p>
    </section>
  );
};

type Props = {
  projectId: string | null;
  versions: VersionInfo[];
  selected: number | null;
  preset: 'preview' | 'final';
  render: RenderState | null;
  now: number;
  spec: SpecOutline | null;
  marks: Record<string, MarkKind>;
  onVersion: (v: number) => void;
  onPreset: (p: 'preview' | 'final') => void;
};

export const VideoPane = (p: Props) => {
  const video = useRef<HTMLVideoElement>(null);
  const v = p.versions.find((x) => x.version === p.selected);
  const files = v ? v[p.preset] : null;
  const url = (kind: string) =>
    p.projectId && p.selected ? api.fileUrl(p.projectId, p.selected, p.preset, kind) : '';
  const rendered = p.versions.filter((x) => x.preview || x.final);
  const scenes: (SceneOutline & { start: number })[] = [];
  for (const s of p.spec?.scenes ?? []) {
    const prev = scenes[scenes.length - 1];
    scenes.push({ ...s, start: prev ? prev.start + (prev.duration_s ?? 0) : 0 });
  }

  return (
    <section className="pane studio" aria-label="Video">
      <div className="studio-bar">
        <label className="field">
          <span>Version</span>
          <select
            aria-label="Version"
            value={p.selected ?? ''}
            disabled={!rendered.length}
            onChange={(e) => p.onVersion(Number(e.target.value))}
          >
            {rendered.length ? null : <option value="">none yet</option>}
            {rendered.map((x) => (
              <option key={x.version} value={x.version}>
                v{x.version}
              </option>
            ))}
          </select>
        </label>
        <div className="segmented" role="radiogroup" aria-label="Preset">
          {(['preview', 'final'] as const).map((k) => (
            <label key={k} className={p.preset === k ? 'is-on' : ''}>
              <input
                type="radio"
                name="preset"
                checked={p.preset === k}
                disabled={!v?.[k]}
                onChange={() => p.onPreset(k)}
              />
              {k === 'preview' ? 'Preview' : 'Final'}
            </label>
          ))}
        </div>
        <nav className="downloads" aria-label="Downloads">
          <a className={files?.mp4 ? '' : 'is-off'} href={files?.mp4 ? url('mp4') : undefined} download>
            Download MP4
          </a>
          <a className={files?.srt ? '' : 'is-off'} href={files?.srt ? url('srt') : undefined} download>
            SRT
          </a>
          <a className={files?.quiz ? '' : 'is-off'} href={files?.quiz ? url('quiz') : undefined} download>
            quiz.json
          </a>
        </nav>
      </div>

      <div className="stage-area">
        <figure className="phone">
          {files?.mp4 ? (
            <video ref={video} key={url('mp4')} controls src={url('mp4')} data-testid="player">
              {files.vtt ? <track kind="captions" src={url('vtt')} default label="Captions" /> : null}
            </video>
          ) : (
            <div className="screen-empty">
              <p>The preview plays here once the script is approved.</p>
            </div>
          )}
        </figure>

        <aside className="scenes" aria-label="Scenes">
          {scenes.length ? (
            <>
              <h3>
                {p.spec?.title}
                <span className="sub">
                  {scenes.length} scenes, {Math.round(p.spec?.total_s ?? 0)} seconds
                </span>
              </h3>
              <ol>
                {scenes.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      disabled={!files?.mp4}
                      title="Play from this scene"
                      onClick={() => {
                        if (!video.current) return;
                        video.current.currentTime = s.start;
                        void video.current.play?.()?.catch(() => undefined);
                      }}
                    >
                      <Mark kind={p.marks[s.id] ?? 'pending'} />
                      <span className="scene-body">
                        <span className="scene-kind">
                          {TEMPLATE[s.template] ?? s.template}
                          <span className="scene-time">{fmtS(s.start)}</span>
                        </span>
                        <span className="scene-text">{(s.texts[0] ?? s.narration).replace(/\*/g, '')}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <p className="scenes-empty">
              Scenes appear here once the script is written, each marked with its fact-check result.
            </p>
          )}
        </aside>
      </div>

      <SpeedPanel r={p.render} now={p.now} />
    </section>
  );
};
