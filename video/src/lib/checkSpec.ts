/**
 * Deterministic layout check of a whole spec: every text box fits (the same fitText + BOXES the
 * templates use), every icon is in the catalog, quiz indices are valid, scene and total durations
 * are sane. The render worker's `check` command returns these issues to the agent.
 */
import { hasIcon } from '../icons/catalog';
import type { Scene, VideoSpec } from '../spec/types';
import { BOXES, CAPTION_BOX, UI_TEXT } from '../templates/boxes';
import { chunkText } from './captions';
import { fitText, type FitBox } from './textFit';

export type Issue = {
  scene_id: string;
  field: string;
  index?: number;
  code: string;
  message: string;
};

export type CheckLimits = { minTotalS: number; maxTotalS: number; minSceneS: number; maxSceneS: number };
export const DEFAULT_LIMITS: CheckLimits = { minTotalS: 30, maxTotalS: 60, minSceneS: 2, maxSceneS: 15 };
/** Minimum seconds a viewer needs to read a quiz question + options before the countdown matters. */
export const MIN_QUIZ_READ_S = 3;

const textFields = (s: Scene): [string, string, FitBox, number?][] => {
  switch (s.template) {
    case 'title_card':
      return [
        ['title', s.title, BOXES.title_card.title],
        ...(s.subtitle
          ? [['subtitle', s.subtitle, BOXES.title_card.subtitle] as [string, string, FitBox]]
          : []),
      ];
    case 'step_card':
      return [['text', s.text, BOXES.step_card.text]];
    case 'do_dont':
      return [
        ['do_text', s.do_text, BOXES.do_dont.do_text],
        ['dont_text', s.dont_text, BOXES.do_dont.dont_text],
      ];
    case 'checklist':
      return [
        ['heading', s.heading, BOXES.checklist.heading],
        ...s.items.map((t, i) => ['items', t, BOXES.checklist.items, i] as [string, string, FitBox, number]),
      ];
    case 'warning':
      return [
        ['heading', s.heading, BOXES.warning.heading],
        ['text', s.text, BOXES.warning.text],
      ];
    case 'timer':
      return [['label', s.label, BOXES.timer.label]];
    case 'schedule':
      return [
        ['heading', s.heading, BOXES.schedule.heading],
        ...s.rows.flatMap((r, i) => [
          ['rows.time', r.time, BOXES.schedule.time, i] as [string, string, FitBox, number],
          ['rows.text', r.text, BOXES.schedule.text, i] as [string, string, FitBox, number],
        ]),
      ];
    case 'quiz_question':
      return [
        ['question', s.question, BOXES.quiz_question.question],
        ...s.options.map(
          (t, i) => ['options', t, BOXES.quiz_question.options, i] as [string, string, FitBox, number],
        ),
      ];
    case 'quiz_answer':
      return [
        ['question', s.question, BOXES.quiz_answer.question],
        ...s.options.map(
          (t, i) => ['options', t, BOXES.quiz_answer.options, i] as [string, string, FitBox, number],
        ),
        ['explanation', s.explanation, BOXES.quiz_answer.explanation],
      ];
    case 'summary':
      return [
        ['heading', s.heading, BOXES.summary.heading],
        ...s.points.map((t, i) => ['points', t, BOXES.summary.points, i] as [string, string, FitBox, number]),
      ];
    case 'disclaimer':
      return [
        ['heading', s.heading, BOXES.disclaimer.heading],
        ['text', s.text, BOXES.disclaimer.text],
      ];
  }
};

const icons = (s: Scene): [string, string, number?][] => {
  switch (s.template) {
    case 'title_card':
      return s.icon ? [['icon', s.icon]] : [];
    case 'step_card':
    case 'warning':
    case 'timer':
      return [['icon', s.icon]];
    case 'do_dont':
      return [
        ['do_icon', s.do_icon],
        ['dont_icon', s.dont_icon],
      ];
    case 'schedule':
      return s.rows.flatMap((r, i) => (r.icon ? [['rows.icon', r.icon, i] as [string, string, number]] : []));
    default:
      return [];
  }
};

const describeFit = (reason: string | undefined, missing?: string[]): string =>
  reason === 'missing_glyph'
    ? `characters the bundled fonts cannot draw: ${missing?.join(' ')}`
    : reason === 'overflow_word'
      ? 'a single word is wider than the box'
      : reason === 'overflow_lines'
        ? 'too long for the box (too many lines)'
        : 'empty text';

export const checkSpec = (spec: VideoSpec, limits: CheckLimits = DEFAULT_LIMITS): Issue[] => {
  const issues: Issue[] = [];
  const add = (i: Issue) => issues.push(i);
  if (!spec.scenes.length)
    add({ scene_id: '-', field: 'scenes', code: 'no_scenes', message: 'spec has no scenes' });
  const ids = new Set<string>();

  for (const s of spec.scenes) {
    if (ids.has(s.id))
      add({ scene_id: s.id, field: 'id', code: 'duplicate_id', message: 'duplicate scene id' });
    ids.add(s.id);

    for (const [field, text, box, index] of textFields(s)) {
      const r = fitText(text, box);
      if (!r.ok) {
        add({
          scene_id: s.id,
          field,
          ...(index !== undefined ? { index } : {}),
          code: `text_${r.reason}`,
          message: `${describeFit(r.reason, r.missing)} (${r.lines.length}/${box.maxLines} lines): "${text}"`,
        });
      }
    }
    for (const [field, name, index] of icons(s)) {
      if (!hasIcon(name))
        add({
          scene_id: s.id,
          field,
          ...(index !== undefined ? { index } : {}),
          code: 'unknown_icon',
          message: `icon "${name}" is not in the catalog`,
        });
    }

    // Narration must be drawable in the caption band, chunk by chunk.
    if (!s.narration.trim())
      add({ scene_id: s.id, field: 'narration', code: 'empty_narration', message: 'narration is empty' });
    for (const chunk of chunkText(s.narration)) {
      const r = fitText(chunk, CAPTION_BOX);
      if (!r.ok)
        add({
          scene_id: s.id,
          field: 'narration',
          code: `caption_${r.reason}`,
          message: `caption chunk cannot be drawn: ${describeFit(r.reason, r.missing)}`,
        });
    }

    if (s.duration_s < limits.minSceneS || s.duration_s > limits.maxSceneS) {
      add({
        scene_id: s.id,
        field: 'duration_s',
        code: 'scene_duration',
        message: `scene lasts ${s.duration_s.toFixed(2)} s (allowed ${limits.minSceneS}-${limits.maxSceneS} s)`,
      });
    }
    if (s.audio && s.audio.start_s + s.audio.duration_s > s.duration_s + 1e-6) {
      add({
        scene_id: s.id,
        field: 'audio',
        code: 'audio_overruns_scene',
        message: `narration ends at ${(s.audio.start_s + s.audio.duration_s).toFixed(2)} s but the scene lasts ${s.duration_s.toFixed(2)} s`,
      });
    }

    if (s.template === 'quiz_question' || s.template === 'quiz_answer') {
      if (s.correct_index < 0 || s.correct_index >= s.options.length) {
        add({
          scene_id: s.id,
          field: 'correct_index',
          code: 'bad_correct_index',
          message: `correct_index ${s.correct_index} is outside the ${s.options.length} options`,
        });
      }
    }
    if (s.template === 'quiz_question') {
      const spoken = s.audio ? s.audio.start_s + s.audio.duration_s : 0;
      if (s.duration_s - s.countdown_s < Math.max(MIN_QUIZ_READ_S, spoken)) {
        add({
          scene_id: s.id,
          field: 'countdown_s',
          code: 'quiz_read_time',
          message: `only ${(s.duration_s - s.countdown_s).toFixed(1)} s before the countdown; need ≥ ${Math.max(MIN_QUIZ_READ_S, spoken).toFixed(1)} s to read and hear the question`,
        });
      }
    }
    if (s.template === 'step_card' && (s.step_no < 1 || s.step_no > s.total_steps)) {
      add({
        scene_id: s.id,
        field: 'step_no',
        code: 'bad_step_no',
        message: `step ${s.step_no} of ${s.total_steps}`,
      });
    }
  }

  const total = spec.scenes.reduce((n, s) => n + s.duration_s, 0);
  if (spec.scenes.length && (total < limits.minTotalS || total > limits.maxTotalS)) {
    add({
      scene_id: '-',
      field: 'duration',
      code: 'total_duration',
      message: `video lasts ${total.toFixed(1)} s (allowed ${limits.minTotalS}-${limits.maxTotalS} s)`,
    });
  }
  if (spec.audience === 'patient' && !spec.scenes.some((s) => s.template === 'disclaimer')) {
    add({
      scene_id: '-',
      field: 'scenes',
      code: 'missing_disclaimer',
      message: 'patient videos must include a disclaimer scene',
    });
  }
  for (const word of Object.values(UI_TEXT[spec.lang])) {
    const r = fitText(word, { width: 2000, maxLines: 1, size: 40, weight: 700 });
    if (!r.ok)
      add({ scene_id: '-', field: 'ui', code: 'ui_text', message: `UI label "${word}" cannot be drawn` });
  }
  return issues;
};
