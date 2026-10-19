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

/** Previews render the same spec at half the frame rate (templates time everything in seconds). */
export const PREVIEW_FPS = 15;

const metadataAt =
  (fps: number): CalculateMetadataFunction<VideoProps> =>
  ({ props }) => {
    // Defence in depth: the worker validated the spec already; validate (and apply defaults) again.
    const parsed = VideoSpecSchema.safeParse(props);
    if (!parsed.success) throw new Error(`invalid video spec:\n${z.prettifyError(parsed.error)}`);
    const spec = parsed.data;
    return { durationInFrames: Math.max(1, Math.round(totalSeconds(spec) * fps)), props: spec };
  };

const Video: React.FC<{ id: string; spec: VideoSpec; fps?: number }> = ({ id, spec, fps = FPS }) => (
  <Composition
    id={id}
    component={InstructionVideo}
    defaultProps={spec as VideoProps}
    calculateMetadata={metadataAt(fps)}
    durationInFrames={Math.max(1, Math.round(totalSeconds(spec) * fps))}
    fps={fps}
    width={WIDTH}
    height={HEIGHT}
  />
);

export const Root: React.FC = () => (
  <>
    <Video id="InstructionVideo" spec={galleryReel('en')} />
    <Video id="InstructionVideoPreview" spec={galleryReel('en')} fps={PREVIEW_FPS} />
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
