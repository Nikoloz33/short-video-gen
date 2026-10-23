/** Plain-language names for what the system is doing — the user never sees internal state names. */

export const STATUS: Record<string, string> = {
  idle: 'Ready',
  need_source: 'Waiting for a document',
  planning: 'Planning the video',
  scripting: 'Writing the script',
  fact_checking: 'Checking facts against your document',
  translating: 'Translating',
  awaiting_script_review: 'Script ready for your review',
  editing: 'Applying your change',
  narrating: 'Recording narration',
  checking_layout: 'Checking that every text fits',
  rendering_preview: 'Rendering the preview',
  awaiting_video_review: 'Preview ready for your review',
  rendering_final: 'Rendering the final video',
  done: 'Final video ready',
  blocked: 'Export blocked by unsupported claims',
  needs_attention: 'Needs your attention',
  refused: 'Request declined',
  error: 'Stopped',
};

export const statusLabel = (s: string): string => STATUS[s] ?? s.replace(/_/g, ' ');

/** Statuses during which the agent is still working (drives the activity indicator). */
export const WORKING = new Set([
  'planning',
  'scripting',
  'fact_checking',
  'translating',
  'editing',
  'narrating',
  'checking_layout',
  'rendering_preview',
  'rendering_final',
]);

export const TEMPLATE: Record<string, string> = {
  title_card: 'Title',
  step_card: 'Step',
  do_dont: 'Do and don’t',
  checklist: 'Checklist',
  warning: 'Warning',
  timer: 'Timer',
  schedule: 'Schedule',
  quiz_question: 'Quiz question',
  quiz_answer: 'Quiz answer',
  summary: 'Summary',
  disclaimer: 'Disclaimer',
};

export type Verdict = 'supported' | 'partially_supported' | 'unsupported' | 'contradicts';

export const VERDICT: Record<string, string> = {
  supported: 'Supported',
  partially_supported: 'Partly supported',
  unsupported: 'Not in the source',
  contradicts: 'Contradicts the source',
};

export const GATE: Record<string, string> = {
  numbers: 'number check',
  names: 'name check',
  polarity: 'negation check',
};
