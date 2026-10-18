/**
 * The one composition: renders any VideoSpec. Scenes play back to back (Series); each scene fades
 * its content in, plays its narration clip at `audio.start_s` and shows the caption chunk that is
 * being spoken. The background and progress bar persist across cuts, so plain cuts look smooth.
 */
import React from 'react';
import {
  AbsoluteFill,
  Html5Audio,
  Sequence,
  Series,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { sceneCues } from './lib/captions';
import type { Scene, VideoSpec } from './spec/types';
import { CAPTION_BOX } from './templates/boxes';
import { FitLines, SceneProvider, useSceneCtx } from './templates/kit';
import { SceneView } from './templates';
import { loadBundledFonts } from './theme/fonts';
import { resolveTheme } from './theme/theme';

loadBundledFonts();

export const totalSeconds = (spec: Pick<VideoSpec, 'scenes'>): number =>
  spec.scenes.reduce((s, sc) => s + sc.duration_s, 0);

const CaptionBand: React.FC<{ scene: Scene }> = ({ scene }) => {
  const { theme } = useSceneCtx();
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const cue = sceneCues(scene).find((c) => t >= c.start && t < c.end);
  if (!cue) return null;
  return (
    <div
      style={{
        position: 'absolute',
        left: theme.safe.side,
        right: theme.safe.side,
        top: theme.safe.captionTop,
        height: theme.safe.captionBottom - theme.safe.captionTop,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <div style={{ background: theme.colors.captionBg, borderRadius: 24, padding: '18px 32px' }}>
        <FitLines text={cue.text} box={CAPTION_BOX} color={theme.colors.captionInk} align="center" />
      </div>
    </div>
  );
};

const ProgressBar: React.FC<{ total: number }> = ({ total }) => {
  const { theme } = useSceneCtx();
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        position: 'absolute',
        left: theme.safe.side,
        right: theme.safe.side,
        top: 70,
        height: 14,
        borderRadius: 7,
        background: theme.colors.bgAlt,
      }}
    >
      <div
        style={{
          width: `${Math.min(100, (frame / Math.max(1, total)) * 100)}%`,
          height: '100%',
          borderRadius: 7,
          background: theme.colors.primary,
        }}
      />
    </div>
  );
};

const SceneShell: React.FC<{ scene: Scene; frames: number }> = ({ scene, frames }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fade = Math.max(1, Math.round(0.2 * fps));
  const opacity = interpolate(frame, [0, fade, frames - fade, frames], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ opacity }}>
        <SceneView scene={scene} />
      </AbsoluteFill>
      <CaptionBand scene={scene} />
      {scene.audio ? (
        <Sequence from={Math.round(scene.audio.start_s * fps)} layout="none">
          <Html5Audio src={scene.audio.src} />
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
};

export const InstructionVideo: React.FC<VideoSpec> = (spec) => {
  const { fps, durationInFrames } = useVideoConfig();
  const theme = resolveTheme(spec.theme);
  return (
    <AbsoluteFill style={{ background: theme.colors.bg }}>
      <SceneProvider value={{ theme, lang: spec.lang, durationInFrames }}>
        <ProgressBar total={durationInFrames} />
      </SceneProvider>
      <Series>
        {spec.scenes.map((scene) => {
          const frames = Math.max(1, Math.round(scene.duration_s * fps));
          return (
            <Series.Sequence key={scene.id} durationInFrames={frames}>
              <SceneProvider value={{ theme, lang: spec.lang, durationInFrames: frames }}>
                <SceneShell scene={scene} frames={frames} />
              </SceneProvider>
            </Series.Sequence>
          );
        })}
      </Series>
    </AbsoluteFill>
  );
};
