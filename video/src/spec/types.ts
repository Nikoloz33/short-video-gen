/**
 * Video spec types. Generated from the agent's Pydantic models (src/generated/spec.ts) — change the
 * contract in agent/schemas/video_spec.py, then run the export + codegen.
 */
import type { VideoSpec } from '../generated/spec';

export type {
  AudioClip,
  ChecklistScene,
  DisclaimerScene,
  DoDontScene,
  QuizAnswerScene,
  QuizQuestionScene,
  ScheduleRow,
  ScheduleScene,
  SourceRef,
  StepCardScene,
  SummaryScene,
  TimerScene,
  TitleCardScene,
  VideoSpec,
  WarningScene,
} from '../generated/spec';

export type Scene = VideoSpec['scenes'][number];
export type Template = Scene['template'];
export type Lang = VideoSpec['lang'];

/** Composition props: the zod-validated spec (a type alias, so Remotion accepts it as props). */
export type VideoProps = import('zod').output<typeof import('../generated/spec.zod').VideoSpecSchema>;
