import React from 'react';
import { AbsoluteFill, Composition, interpolate, useCurrentFrame } from 'remotion';
import { FPS, HEIGHT, WIDTH } from './lib/time';

/** Placeholder until the scene templates land: a flat title card used by the smoke render. */
const Placeholder: React.FC<{ title: string }> = ({ title }) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 15], [0, 1], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill style={{ background: '#0f3b5f', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ color: 'white', fontSize: 96, fontFamily: 'sans-serif', fontWeight: 700, opacity }}>
        {title}
      </div>
    </AbsoluteFill>
  );
};

export const Root: React.FC = () => (
  <Composition
    id="Placeholder"
    component={Placeholder}
    defaultProps={{ title: 'InstructVid' }}
    durationInFrames={2 * FPS}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
  />
);
