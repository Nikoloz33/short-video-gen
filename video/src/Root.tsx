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
import { z } from 'zod';
import { GALLERY, TEMPLATES, galleryId, gallerySpec, galleryReel } from './examples/gallery';
import { VideoSpecSchema } from './generated/spec.zod';
import { IconSheet } from './IconSheet';
import { InstructionVideo, totalSeconds } from './InstructionVideo';
import { FPS, HEIGHT, WIDTH } from './lib/time';
import type { Lang, VideoProps, VideoSpec } from './spec/types';

const calculateMetadata: CalculateMetadataFunction<VideoProps> = ({ props }) => {
  // Defence in depth: the worker validated the spec already; validate (and apply defaults) again.
  const parsed = VideoSpecSchema.safeParse(props);
  if (!parsed.success) throw new Error(`invalid video spec:\n${z.prettifyError(parsed.error)}`);
  const spec = parsed.data;
  return { durationInFrames: Math.max(1, Math.round(totalSeconds(spec) * FPS)), props: spec };
};

const Video: React.FC<{ id: string; spec: VideoSpec }> = ({ id, spec }) => (
  <Composition
    id={id}
    component={InstructionVideo}
    defaultProps={spec as VideoProps}
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
