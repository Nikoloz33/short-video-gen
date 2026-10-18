/**
 * Quiz checkpoint: QuizQuestion (question + 2-4 options + countdown ring over the last
 * `countdown_s` seconds) then QuizAnswer (correct option highlighted + one-line explanation).
 */
import React from 'react';
import { useCurrentFrame } from 'remotion';
import { Icon } from '../icons/Icon';
import type { QuizAnswerScene, QuizQuestionScene } from '../spec/types';
import { BOXES, OPTION_LETTERS, UI_TEXT } from './boxes';
import { Appear, Card, FitLines, Pill, Ring, Stack, useProgress, useSceneCtx, useSec } from './kit';

type OptionState = 'idle' | 'correct' | 'dimmed';

const Option: React.FC<{ letter: string; text: string; state: OptionState; delay: number }> = ({
  letter,
  text,
  state,
  delay,
}) => {
  const { theme } = useSceneCtx();
  const c = theme.colors;
  const correct = state === 'correct';
  return (
    <Appear delay={delay} motion="left" style={{ width: '100%', opacity: state === 'dimmed' ? 0.45 : 1 }}>
      <Card
        pad={28}
        bg={correct ? c.okSoft : c.surface}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 28,
          outline: correct ? `6px solid ${c.ok}` : undefined,
        }}
      >
        <div
          style={{
            width: 84,
            height: 84,
            borderRadius: 42,
            flexShrink: 0,
            background: correct ? c.ok : c.bgAlt,
            color: correct ? c.surface : c.ink,
            fontFamily: theme.font.family,
            fontWeight: 700,
            fontSize: 44,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {correct ? <Icon name="check" size={52} color={c.surface} strokeWidth={3} /> : letter}
        </div>
        <FitLines text={text} box={BOXES.quiz_question.options} />
      </Card>
    </Appear>
  );
};

export const QuizQuestion: React.FC<{ scene: QuizQuestionScene }> = ({ scene }) => {
  const { theme, lang, durationInFrames } = useSceneCtx();
  const frame = useCurrentFrame();
  const sec = useSec();
  const cdStart = Math.max(0, durationInFrames - sec(scene.countdown_s));
  const counting = frame >= cdStart;
  const p = counting ? 1 - (frame - cdStart) / Math.max(1, durationInFrames - cdStart) : 1;
  const left = Math.max(0, Math.ceil(scene.countdown_s * p));
  return (
    <Stack gap={30} align="flex-start">
      <div style={{ display: 'flex', width: '100%', alignItems: 'center', justifyContent: 'space-between' }}>
        <Appear delay={0} motion="fade">
          <Pill text={UI_TEXT[lang].quiz} bg={theme.colors.accent} fg={theme.colors.ink} />
        </Appear>
        <Appear delay={0.2} motion="scale">
          <Ring
            size={150}
            stroke={16}
            p={p}
            color={counting ? theme.colors.bad : theme.colors.primary}
            track={theme.colors.bgAlt}
          >
            <div
              style={{
                fontFamily: theme.font.family,
                fontWeight: 700,
                fontSize: 64,
                color: theme.colors.ink,
              }}
            >
              {left}
            </div>
          </Ring>
        </Appear>
      </div>
      <Appear delay={0.15}>
        <FitLines text={scene.question} box={BOXES.quiz_question.question} />
      </Appear>
      {scene.options.map((o, i) => (
        <Option key={i} letter={OPTION_LETTERS[i] ?? '?'} text={o} state="idle" delay={0.5 + i * 0.25} />
      ))}
    </Stack>
  );
};

export const QuizAnswer: React.FC<{ scene: QuizAnswerScene }> = ({ scene }) => {
  const { theme, lang } = useSceneCtx();
  const reveal = useProgress(0.4, 0.3);
  return (
    <Stack gap={28} align="flex-start">
      <Appear delay={0} motion="fade">
        <Pill text={UI_TEXT[lang].answer} bg={theme.colors.ok} fg={theme.colors.surface} />
      </Appear>
      <FitLines text={scene.question} box={BOXES.quiz_answer.question} color={theme.colors.muted} />
      {scene.options.map((o, i) => (
        <Option
          key={i}
          letter={OPTION_LETTERS[i] ?? '?'}
          text={o}
          delay={0}
          state={reveal < 0.5 ? 'idle' : i === scene.correct_index ? 'correct' : 'dimmed'}
        />
      ))}
      <Appear delay={0.8}>
        <FitLines text={scene.explanation} box={BOXES.quiz_answer.explanation} style={{ marginTop: 12 }} />
      </Appear>
    </Stack>
  );
};
