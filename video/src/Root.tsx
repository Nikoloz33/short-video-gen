/**
 * Compositions:
 *  - "InstructionVideo": renders any VideoSpec passed as input props (the render worker uses this);
 *  - "Gallery-<template>-<lang>": one example scene per template, for Studio + stills/snapshots;
 *  - "Reel-<lang>": all templates back to back;
 *  - "IconSheet": the icon catalog at a glance.
 * Duration always comes from the spec (calculateMetadata).
 */
import React from 'react';
import { Composition, Still, type CalculateMetadataFunction } from 'remotion';
import { GALLERY, TEMPLATES, galleryId, gallerySpec, galleryReel } from './examples/gallery';
import { IconSheet } from './IconSheet';
import { InstructionVideo, totalSeconds } from './InstructionVideo';
import { FPS, HEIGHT, WIDTH } from './lib/time';
import type { Lang, VideoSpec } from './spec/types';

const calculateMetadata: CalculateMetadataFunction<VideoSpec> = ({ props }) => ({
  durationInFrames: Math.max(1, Math.round(totalSeconds(props) * FPS)),
});

const Video: React.FC<{ id: string; spec: VideoSpec }> = ({ id, spec }) => (
  <Composition
    id={id}
    component={InstructionVideo}
    defaultProps={spec}
    calculateMetadata={calculateMetadata}
    durationInFrames={Math.max(1, Math.round(totalSeconds(spec) * FPS))}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
  />
);

export const Root: React.FC = () => (
  <>
    <Video id="InstructionVideo" spec={galleryReel('en')} />
    {(Object.keys(GALLERY) as Lang[]).map((lang) => (
      <React.Fragment key={lang}>
        <Video id={`Reel-${lang}`} spec={galleryReel(lang)} />
        {TEMPLATES.map((t) => (
          <Video key={t} id={galleryId(t, lang)} spec={gallerySpec(lang, t)} />
        ))}
      </React.Fragment>
    ))}
    <Still id="IconSheet" component={IconSheet} width={WIDTH} height={HEIGHT} />
  </>
);
