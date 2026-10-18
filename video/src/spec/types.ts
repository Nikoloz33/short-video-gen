/**
 * Video spec types used by the templates. Field names follow the agent's JSON (snake_case).
 */
export type Lang = 'ka' | 'en';

export type AudioClip = {
  /** URL (http:// from the render worker, or a staticFile path in Studio examples). */
  src: string;
  /** Measured clip length in seconds. */
  duration_s: number;
  /** When the clip starts, relative to the scene start. */
  start_s: number;
};

type SceneBase = {
  id: string;
  narration: string;
  evidence: string[];
  duration_s: number;
  audio?: AudioClip | null;
};

export type TitleCardScene = SceneBase & {
  template: 'title_card';
  title: string;
  subtitle?: string | null;
  icon?: string | null;
};
export type StepCardScene = SceneBase & {
  template: 'step_card';
  step_no: number;
  total_steps: number;
  icon: string;
  text: string;
};
export type DoDontScene = SceneBase & {
  template: 'do_dont';
  do_text: string;
  do_icon: string;
  dont_text: string;
  dont_icon: string;
};
export type ChecklistScene = SceneBase & { template: 'checklist'; heading: string; items: string[] };
export type WarningScene = SceneBase & { template: 'warning'; heading: string; text: string; icon: string };
export type TimerScene = SceneBase & { template: 'timer'; label: string; seconds: number; icon: string };
export type ScheduleRow = { time: string; text: string; icon?: string | null };
export type ScheduleScene = SceneBase & { template: 'schedule'; heading: string; rows: ScheduleRow[] };
export type QuizQuestionScene = SceneBase & {
  template: 'quiz_question';
  question: string;
  options: string[];
  correct_index: number;
  countdown_s: number;
};
export type QuizAnswerScene = SceneBase & {
  template: 'quiz_answer';
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
};
export type SummaryScene = SceneBase & { template: 'summary'; heading: string; points: string[] };
export type DisclaimerScene = SceneBase & { template: 'disclaimer'; heading: string; text: string };

export type Scene =
  | TitleCardScene
  | StepCardScene
  | DoDontScene
  | ChecklistScene
  | WarningScene
  | TimerScene
  | ScheduleScene
  | QuizQuestionScene
  | QuizAnswerScene
  | SummaryScene
  | DisclaimerScene;

export type Template = Scene['template'];

export type SourceRef = { doc_id: string; title: string };

export type VideoSpec = {
  version: number;
  title: string;
  lang: Lang;
  source_lang: Lang;
  audience: 'workplace' | 'patient';
  voice: string;
  theme: string;
  target_sec: number;
  scenes: Scene[];
  sources: SourceRef[];
};
