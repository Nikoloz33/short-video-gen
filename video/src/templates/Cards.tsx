/** Single-message templates: TitleCard, StepCard, Warning, Timer, Disclaimer. */
import React from 'react';
import { useCurrentFrame } from 'remotion';
import type { DisclaimerScene, StepCardScene, TimerScene, TitleCardScene, WarningScene } from '../spec/types';
import { BOXES, UI_TEXT } from './boxes';
import {
  Appear,
  Card,
  FitLines,
  IconBadge,
  Pill,
  Ring,
  Stack,
  usePop,
  useProgress,
  useSceneCtx,
  useSec,
} from './kit';

export const TitleCard: React.FC<{ scene: TitleCardScene }> = ({ scene }) => {
  const { theme } = useSceneCtx();
  const pop = usePop(0.1);
  return (
    <Stack gap={56}>
      {scene.icon ? (
        <IconBadge
          name={scene.icon}
          size={300}
          bg={theme.colors.primary}
          fg={theme.colors.primaryInk}
          scale={pop}
        />
      ) : null}
      <Appear delay={0.3}>
        <FitLines text={scene.title} box={BOXES.title_card.title} align="center" />
      </Appear>
      {scene.subtitle ? (
        <Appear delay={0.6}>
          <FitLines
            text={scene.subtitle}
            box={BOXES.title_card.subtitle}
            align="center"
            color={theme.colors.muted}
          />
        </Appear>
      ) : null}
    </Stack>
  );
};

const StepDots: React.FC<{ n: number; total: number }> = ({ n, total }) => {
  const { theme } = useSceneCtx();
  return (
    <div style={{ display: 'flex', gap: 18 }}>
      {Array.from({ length: total }, (_, i) => (
        <div
          key={i}
          style={{
            width: i + 1 === n ? 56 : 22,
            height: 22,
            borderRadius: 11,
            background: i + 1 <= n ? theme.colors.primary : theme.colors.bgAlt,
          }}
        />
      ))}
    </div>
  );
};

export const StepCard: React.FC<{ scene: StepCardScene }> = ({ scene }) => {
  const { theme, lang } = useSceneCtx();
  const pop = usePop(0.25);
  return (
    <Stack gap={48}>
      <Appear delay={0} motion="fade">
        <Pill
          text={`${UI_TEXT[lang].step} ${scene.step_no} / ${scene.total_steps}`}
          bg={theme.colors.primary}
          fg={theme.colors.primaryInk}
        />
      </Appear>
      <Card pad={60} style={{ transform: `scale(${0.9 + 0.1 * pop})` }}>
        <IconBadge
          name={scene.icon}
          size={360}
          bg={theme.colors.bgAlt}
          fg={theme.colors.primary}
          scale={pop}
        />
      </Card>
      <Appear delay={0.45}>
        <FitLines text={scene.text} box={BOXES.step_card.text} align="center" />
      </Appear>
      <Appear delay={0.6} motion="fade">
        <StepDots n={scene.step_no} total={scene.total_steps} />
      </Appear>
    </Stack>
  );
};

/** Yellow/black hazard stripes. */
const Stripes: React.FC<{ height: number }> = ({ height }) => {
  const { theme } = useSceneCtx();
  return (
    <div
      style={{
        height,
        borderRadius: 12,
        background: `repeating-linear-gradient(-45deg, ${theme.colors.warn} 0 40px, ${theme.colors.warnInk} 40px 80px)`,
      }}
    />
  );
};

export const Warning: React.FC<{ scene: WarningScene }> = ({ scene }) => {
  const { theme, lang } = useSceneCtx();
  const frame = useCurrentFrame();
  const sec = useSec();
  const pop = usePop(0.15);
  // A slow pulse ring behind the icon draws the eye without flashing.
  const pulse = 1 + 0.06 * Math.sin((frame / sec(1.2)) * Math.PI * 2);
  return (
    <Stack gap={44}>
      <Appear delay={0} motion="fade" style={{ width: '100%' }}>
        <Stripes height={44} />
      </Appear>
      <div style={{ transform: `scale(${pulse})` }}>
        <IconBadge
          name={scene.icon}
          size={300}
          bg={theme.colors.warn}
          fg={theme.colors.warnInk}
          scale={pop}
        />
      </div>
      <Card pad={40} style={{ borderTop: `14px solid ${theme.colors.warn}` }}>
        <Appear delay={0.3}>
          <div
            style={{
              fontFamily: theme.font.family,
              fontSize: 38,
              fontWeight: 700,
              color: theme.colors.bad,
              marginBottom: 10,
            }}
          >
            {UI_TEXT[lang].warning}
          </div>
          <FitLines text={scene.heading} box={BOXES.warning.heading} />
        </Appear>
        <Appear delay={0.55}>
          <FitLines
            text={scene.text}
            box={BOXES.warning.text}
            color={theme.colors.muted}
            style={{ marginTop: 18 }}
          />
        </Appear>
      </Card>
      <Appear delay={0} motion="fade" style={{ width: '100%' }}>
        <Stripes height={44} />
      </Appear>
    </Stack>
  );
};

export const Timer: React.FC<{ scene: TimerScene }> = ({ scene }) => {
  const { theme, lang, durationInFrames } = useSceneCtx();
  const frame = useCurrentFrame();
  const sec = useSec();
  // The ring empties over the scene (minus entrance and a held end): the count is shown accelerated
  // when the real duration is longer than the scene.
  const start = sec(0.6);
  const end = Math.max(start + 1, durationInFrames - sec(0.6));
  const p = 1 - Math.min(1, Math.max(0, (frame - start) / (end - start)));
  const remaining = Math.ceil(scene.seconds * p);
  return (
    <Stack gap={56}>
      <Appear delay={0}>
        <FitLines text={scene.label} box={BOXES.timer.label} align="center" />
      </Appear>
      <Appear delay={0.2} motion="scale">
        <Ring size={560} stroke={40} p={p} color={theme.colors.primary} track={theme.colors.bgAlt}>
          <div
            style={{
              fontFamily: theme.font.family,
              fontWeight: 700,
              fontSize: 200,
              color: theme.colors.ink,
              lineHeight: 1,
            }}
          >
            {remaining}
          </div>
          <div style={{ fontFamily: theme.font.family, fontSize: 48, color: theme.colors.muted }}>
            {UI_TEXT[lang].seconds}
          </div>
        </Ring>
      </Appear>
      <Appear delay={0.4} motion="fade">
        <IconBadge name={scene.icon} size={180} bg={theme.colors.surface} fg={theme.colors.primary} />
      </Appear>
    </Stack>
  );
};

export const Disclaimer: React.FC<{ scene: DisclaimerScene }> = ({ scene }) => {
  const { theme } = useSceneCtx();
  const p = useProgress(0.1);
  return (
    <Stack gap={44}>
      <div style={{ opacity: p }}>
        <IconBadge name="info" size={200} bg={theme.colors.bgAlt} fg={theme.colors.primary} />
      </div>
      <Card pad={40} style={{ opacity: p }}>
        <FitLines text={scene.heading} box={BOXES.disclaimer.heading} />
        <FitLines
          text={scene.text}
          box={BOXES.disclaimer.text}
          color={theme.colors.muted}
          style={{ marginTop: 24 }}
        />
      </Card>
    </Stack>
  );
};
