import React from 'react';
import { AbsoluteFill, Composition, Still, interpolate, useCurrentFrame } from 'remotion';
import { IconSheet } from './IconSheet';
import { FPS, HEIGHT, WIDTH } from './lib/time';
import { loadBundledFonts } from './theme/fonts';
import { DEFAULT_THEME as T } from './theme/theme';

loadBundledFonts();

/** Placeholder until the scene templates land: a flat title card used by the smoke render. */
const Placeholder: React.FC<{ title: string }> = ({ title }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ background: T.colors.primary, alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ color: 'white', fontSize: 96, fontFamily: T.font.family, fontWeight: 700, opacity }}>
        {title}
      </div>
    </AbsoluteFill>
  );
};

export const Root: React.FC = () => (
  <>
    <Composition
      id="Placeholder"
      component={Placeholder}
      defaultProps={{ title: 'InstructVid' }}
      durationInFrames={2 * FPS}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
    <Still id="IconSheet" component={IconSheet} width={WIDTH} height={HEIGHT} />
  </>
);
