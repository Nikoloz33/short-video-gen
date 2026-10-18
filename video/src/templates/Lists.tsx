/** Multi-item templates: DoDont, Checklist, Schedule, Summary. Items enter one by one. */
import React from 'react';
import { Icon } from '../icons/Icon';
import type { ChecklistScene, DoDontScene, ScheduleScene, SummaryScene } from '../spec/types';
import { BOXES, UI_TEXT } from './boxes';
import { Appear, Card, FitLines, IconBadge, Pill, Stack, useProgress, useSceneCtx, useSec } from './kit';

const Panel: React.FC<{ good: boolean; icon: string; text: string; delay: number }> = ({
  good,
  icon,
  text,
  delay,
}) => {
  const { theme, lang } = useSceneCtx();
  const c = theme.colors;
  return (
    <Appear delay={delay} motion={good ? 'left' : 'right'} style={{ width: '100%' }}>
      <Card
        bg={good ? c.okSoft : c.badSoft}
        pad={36}
        style={{ borderLeft: `16px solid ${good ? c.ok : c.bad}` }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 20 }}>
          <Icon name={good ? 'circle-check' : 'circle-x'} size={56} color={good ? c.ok : c.bad} />
          <div
            style={{
              fontFamily: theme.font.family,
              fontWeight: 700,
              fontSize: 44,
              color: good ? c.ok : c.bad,
            }}
          >
            {good ? UI_TEXT[lang].do : UI_TEXT[lang].dont}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 34 }}>
          <IconBadge name={icon} size={140} bg={c.surface} fg={good ? c.ok : c.bad} />
          <FitLines text={text} box={good ? BOXES.do_dont.do_text : BOXES.do_dont.dont_text} />
        </div>
      </Card>
    </Appear>
  );
};

export const DoDont: React.FC<{ scene: DoDontScene }> = ({ scene }) => (
  <Stack gap={48}>
    <Panel good icon={scene.do_icon} text={scene.do_text} delay={0.1} />
    <Panel good={false} icon={scene.dont_icon} text={scene.dont_text} delay={0.9} />
  </Stack>
);

/** Even spacing of item entrances over the first ~70 % of the scene. */
const useItemDelays = (n: number, first = 0.5): number[] => {
  const { durationInFrames } = useSceneCtx();
  const sec = useSec();
  const span = Math.max(0.6, (durationInFrames / sec(1)) * 0.7 - first);
  return Array.from({ length: n }, (_, i) => first + (n > 1 ? (span * i) / (n - 1) : 0));
};

const CheckBox: React.FC<{ delay: number }> = ({ delay }) => {
  const { theme } = useSceneCtx();
  const p = useProgress(delay + 0.25, 0.3);
  return (
    <div
      style={{
        width: 80,
        height: 80,
        borderRadius: 18,
        border: `6px solid ${theme.colors.ok}`,
        background: p > 0.5 ? theme.colors.ok : theme.colors.surface,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}
    >
      <div style={{ transform: `scale(${p})` }}>
        <Icon name="check" size={56} color={theme.colors.surface} strokeWidth={3} />
      </div>
    </div>
  );
};

export const Checklist: React.FC<{ scene: ChecklistScene }> = ({ scene }) => {
  const delays = useItemDelays(scene.items.length);
  return (
    <Stack gap={32} align="flex-start">
      <Appear delay={0}>
        <FitLines text={scene.heading} box={BOXES.checklist.heading} />
      </Appear>
      {scene.items.map((item, i) => (
        <Appear key={i} delay={delays[i] ?? 0} motion="left">
          <div style={{ display: 'flex', alignItems: 'center', gap: 30 }}>
            <CheckBox delay={delays[i] ?? 0} />
            <FitLines text={item} box={BOXES.checklist.items} />
          </div>
        </Appear>
      ))}
    </Stack>
  );
};

export const Schedule: React.FC<{ scene: ScheduleScene }> = ({ scene }) => {
  const { theme } = useSceneCtx();
  const delays = useItemDelays(scene.rows.length);
  return (
    <Stack gap={28} align="flex-start">
      <Appear delay={0}>
        <FitLines text={scene.heading} box={BOXES.schedule.heading} />
      </Appear>
      {scene.rows.map((row, i) => (
        <Appear key={i} delay={delays[i] ?? 0} motion="up" style={{ width: '100%' }}>
          <Card pad={28} style={{ display: 'flex', alignItems: 'center', gap: 30 }}>
            <div
              style={{
                width: 240,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 8,
                flexShrink: 0,
              }}
            >
              {row.icon ? <Icon name={row.icon} size={64} color={theme.colors.primary} /> : null}
              <FitLines
                text={row.time}
                box={BOXES.schedule.time}
                align="center"
                color={theme.colors.primary}
              />
            </div>
            <FitLines text={row.text} box={BOXES.schedule.text} />
          </Card>
        </Appear>
      ))}
    </Stack>
  );
};

export const Summary: React.FC<{ scene: SummaryScene }> = ({ scene }) => {
  const { theme, lang } = useSceneCtx();
  const delays = useItemDelays(scene.points.length, 0.6);
  return (
    <Stack gap={36} align="flex-start">
      <Appear delay={0} motion="fade">
        <Pill text={UI_TEXT[lang].remember} bg={theme.colors.accent} fg={theme.colors.ink} />
      </Appear>
      <Appear delay={0.15}>
        <FitLines text={scene.heading} box={BOXES.summary.heading} />
      </Appear>
      {scene.points.map((pt, i) => (
        <Appear key={i} delay={delays[i] ?? 0} motion="left">
          <div style={{ display: 'flex', alignItems: 'center', gap: 30 }}>
            <IconBadge name="check" size={72} bg={theme.colors.ok} fg={theme.colors.surface} />
            <FitLines text={pt} box={BOXES.summary.points} />
          </div>
        </Appear>
      ))}
    </Stack>
  );
};
