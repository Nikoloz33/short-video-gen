/**
 * Shared template building blocks: themed context, fitted text, cheap motion (fade / slide / scale /
 * tick-in / ring), icon badges. No particles, filters or per-pixel effects — renders stay fast.
 */
import React, { createContext, useContext } from 'react';
import { Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from 'remotion';
import { Icon } from '../icons/Icon';
import { fitText, segmentLines, type FitBox } from '../lib/textFit';
import type { Lang } from '../spec/types';
import { DEFAULT_THEME, type Theme } from '../theme/theme';

export type SceneCtx = { theme: Theme; lang: Lang; durationInFrames: number };
const Ctx = createContext<SceneCtx>({ theme: DEFAULT_THEME, lang: 'en', durationInFrames: 150 });
export const SceneProvider = Ctx.Provider;
export const useSceneCtx = (): SceneCtx => useContext(Ctx);

/** Seconds -> frames at the composition's fps (previews may render at a different fps). */
export const useSec = (): ((s: number) => number) => {
  const { fps } = useVideoConfig();
  return (s: number) => Math.round(s * fps);
};

/** 0 -> 1 over `dur` seconds starting at `delay` seconds, eased out. */
export const useProgress = (delay: number, dur = 0.45): number => {
  const frame = useCurrentFrame();
  const sec = useSec();
  return interpolate(frame, [sec(delay), sec(delay) + Math.max(1, sec(dur))], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
};

/** A springy 0 -> ~1 scale for icon pops. */
export const usePop = (delay: number): number => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({
    frame: frame - Math.round(delay * fps),
    fps,
    config: { damping: 12, stiffness: 140, mass: 0.6 },
  });
};

type Motion = 'fade' | 'up' | 'left' | 'right' | 'scale';

export const Appear: React.FC<{
  delay: number;
  dur?: number;
  motion?: Motion;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ delay, dur = 0.45, motion = 'up', style, children }) => {
  const p = useProgress(delay, dur);
  const d = (1 - p) * 60;
  const transform =
    motion === 'up'
      ? `translateY(${d}px)`
      : motion === 'left'
        ? `translateX(${-d * 2}px)`
        : motion === 'right'
          ? `translateX(${d * 2}px)`
          : motion === 'scale'
            ? `scale(${0.85 + 0.15 * p})`
            : undefined;
  return <div style={{ opacity: p, transform, ...style }}>{children}</div>;
};

/**
 * Text laid out by fitText() — one block per line — so the render matches the validated layout.
 * Throws when the text does not fit: a spec that reaches rendering must have passed checkSpec().
 */
export const FitLines: React.FC<{
  text: string;
  box: FitBox;
  color?: string;
  highlight?: string;
  align?: 'left' | 'center';
  style?: React.CSSProperties;
}> = ({ text, box, color, highlight, align = 'left', style }) => {
  const { theme } = useSceneCtx();
  const fit = fitText(text, box);
  if (!fit.ok) throw new Error(`text does not fit (${fit.reason}): "${text}"`);
  return (
    <div
      style={{
        fontFamily: theme.font.family,
        fontSize: box.size,
        fontWeight: box.weight,
        lineHeight: theme.lineHeight,
        color: color ?? theme.colors.ink,
        textAlign: align,
        width: box.width,
        ...style,
      }}
    >
      {segmentLines(fit.lines).map((segs, i) => (
        <div key={i} style={{ whiteSpace: 'pre' }}>
          {segs.map((s, j) => (
            <span key={j} style={s.hl ? { color: highlight ?? theme.colors.primary } : undefined}>
              {s.text}
            </span>
          ))}
        </div>
      ))}
    </div>
  );
};

/** Round badge with a centred icon. */
export const IconBadge: React.FC<{ name: string; size: number; bg: string; fg: string; scale?: number }> = ({
  name,
  size,
  bg,
  fg,
  scale = 1,
}) => (
  <div
    style={{
      width: size,
      height: size,
      borderRadius: size / 2,
      background: bg,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      transform: `scale(${scale})`,
      flexShrink: 0,
    }}
  >
    <Icon name={name} size={size * 0.56} color={fg} strokeWidth={2} />
  </div>
);

/** A label pill (badges such as "Step 2 / 5", "Quick quiz"). */
export const Pill: React.FC<{ text: string; bg: string; fg: string; size?: number }> = ({
  text,
  bg,
  fg,
  size = 40,
}) => {
  const { theme } = useSceneCtx();
  return (
    <div
      style={{
        display: 'inline-block',
        background: bg,
        color: fg,
        fontFamily: theme.font.family,
        fontWeight: 700,
        fontSize: size,
        padding: `${size * 0.3}px ${size * 0.7}px`,
        borderRadius: size,
        letterSpacing: 1,
      }}
    >
      {text}
    </div>
  );
};

/** Circular progress ring (timer / countdown). `p` = remaining fraction 1 -> 0. */
export const Ring: React.FC<{
  size: number;
  stroke: number;
  p: number;
  color: string;
  track: string;
  children?: React.ReactNode;
}> = ({ size, stroke, p, color, track, children }) => {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} style={{ position: 'absolute', inset: 0, transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={track} strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.max(0, Math.min(1, p)))}
        />
      </svg>
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
        }}
      >
        {children}
      </div>
    </div>
  );
};

/** Content column of a scene: centred vertically inside the theme's content area. */
export const Stack: React.FC<{
  gap?: number;
  align?: 'center' | 'flex-start';
  children: React.ReactNode;
}> = ({ gap = 40, align = 'center', children }) => {
  const { theme } = useSceneCtx();
  return (
    <div
      style={{
        position: 'absolute',
        left: theme.safe.side,
        right: theme.safe.side,
        top: theme.safe.top,
        height: theme.safe.contentBottom - theme.safe.top,
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        alignItems: align,
        gap,
      }}
    >
      {children}
    </div>
  );
};

export const Card: React.FC<{
  bg?: string;
  pad?: number;
  style?: React.CSSProperties;
  children: React.ReactNode;
}> = ({ bg, pad = 40, style, children }) => {
  const { theme } = useSceneCtx();
  return (
    <div
      style={{
        background: bg ?? theme.colors.surface,
        borderRadius: theme.radius,
        padding: pad,
        boxShadow: '0 8px 0 rgba(19, 33, 46, 0.08)',
        ...style,
      }}
    >
      {children}
    </div>
  );
};
