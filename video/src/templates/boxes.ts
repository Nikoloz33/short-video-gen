/**
 * Every text box of every template: width (px), max lines, font size, weight. Templates lay text
 * out with exactly these boxes and checkSpec() validates against them, so a spec that passes the
 * check renders without overflow. List fields (items, options, points, rows) apply per element.
 */
import type { FitBox } from '../lib/textFit';
import type { Lang, Template } from '../spec/types';

const b = (width: number, maxLines: number, size: number, weight: 400 | 700): FitBox => ({
  width,
  maxLines,
  size,
  weight,
});

export const BOXES = {
  title_card: { title: b(920, 3, 92, 700), subtitle: b(920, 2, 52, 400) },
  step_card: { text: b(920, 3, 64, 700) },
  do_dont: { do_text: b(640, 3, 52, 700), dont_text: b(640, 3, 52, 700) },
  checklist: { heading: b(920, 2, 72, 700), items: b(780, 2, 50, 400) },
  warning: { heading: b(840, 2, 76, 700), text: b(840, 3, 54, 400) },
  timer: { label: b(920, 2, 64, 700) },
  schedule: { heading: b(920, 2, 72, 700), time: b(240, 2, 40, 700), text: b(580, 2, 46, 400) },
  quiz_question: { question: b(920, 3, 62, 700), options: b(740, 2, 48, 400) },
  quiz_answer: { question: b(920, 2, 42, 400), options: b(740, 2, 48, 400), explanation: b(920, 3, 50, 400) },
  summary: { heading: b(920, 2, 72, 700), points: b(780, 2, 50, 400) },
  disclaimer: { heading: b(840, 2, 64, 700), text: b(840, 6, 46, 400) },
} satisfies Record<Template, Record<string, FitBox>>;

/** Burned-in caption band: one chunk of narration at a time. */
export const CAPTION_BOX: FitBox = b(856, 2, 44, 700);

/** Fixed UI words drawn by the templates (badges, labels). */
export const UI_TEXT: Record<
  Lang,
  Record<'step' | 'do' | 'dont' | 'quiz' | 'answer' | 'remember' | 'warning' | 'seconds', string>
> = {
  en: {
    step: 'Step',
    do: 'DO',
    dont: "DON'T",
    quiz: 'Quick quiz',
    answer: 'Answer',
    remember: 'Remember',
    warning: 'WARNING',
    seconds: 'seconds',
  },
  ka: {
    step: 'ნაბიჯი',
    do: 'სწორია',
    dont: 'არ შეიძლება',
    quiz: 'მოკლე ქვიზი',
    answer: 'პასუხი',
    remember: 'დაიმახსოვრეთ',
    warning: 'ყურადღება',
    seconds: 'წამი',
  },
};

/** Option letters for quiz cards (Latin in both languages, as on printed tests). */
export const OPTION_LETTERS = ['A', 'B', 'C', 'D'];
