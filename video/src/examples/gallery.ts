/**
 * One example scene per template in English and Georgian: Studio previews, stills and the
 * snapshot tests render these. Content is illustrative only (not fact-checked).
 */
import type { Lang, Scene, Template, VideoSpec } from '../spec/types';

type DistOmit<T, K extends PropertyKey> = T extends unknown ? Omit<T, K> : never;
type Ex = DistOmit<Scene, 'id' | 'evidence' | 'audio'>;

const en: Record<Template, Ex> = {
  title_card: {
    template: 'title_card',
    title: 'How to wash your hands',
    subtitle: 'Kitchen hygiene · 6 steps',
    icon: 'hand-wash',
    narration: 'In this video you will learn how to wash your hands correctly.',
    duration_s: 4,
  },
  step_card: {
    template: 'step_card',
    step_no: 1,
    total_steps: 6,
    icon: 'droplets',
    text: 'Wet your hands with *clean running water*',
    narration: 'Step one: wet your hands with clean running water.',
    duration_s: 4,
  },
  do_dont: {
    template: 'do_dont',
    do_text: 'Dry hands with a *single-use* paper towel',
    do_icon: 'wind',
    dont_text: 'Never wipe your hands on your *apron*',
    dont_icon: 'apron',
    narration: 'Dry your hands with a single-use towel, and never wipe them on your apron.',
    duration_s: 5,
  },
  checklist: {
    template: 'checklist',
    heading: 'Before you start',
    items: ['Remove rings and watches', 'Roll up your sleeves', 'Check that soap is available'],
    narration:
      'Before you start, remove rings and watches, roll up your sleeves and check that soap is available.',
    duration_s: 6,
  },
  warning: {
    template: 'warning',
    heading: 'Hot water can scald',
    text: 'Check the temperature before you put your hands under the tap.',
    icon: 'flame',
    narration: 'Careful: hot water can scald. Check the temperature first.',
    duration_s: 4.5,
  },
  timer: {
    template: 'timer',
    label: 'Scrub for at least *20 seconds*',
    seconds: 20,
    icon: 'soap',
    narration: 'Scrub all surfaces of your hands for at least twenty seconds.',
    duration_s: 5,
  },
  schedule: {
    template: 'schedule',
    heading: 'Medication schedule',
    rows: [
      { time: '08:00', text: '1 tablet with breakfast', icon: 'sun' },
      { time: '20:00', text: '1 tablet after dinner', icon: 'moon' },
    ],
    narration: 'Take one tablet with breakfast at eight and one after dinner at twenty hundred.',
    duration_s: 5,
  },
  quiz_question: {
    template: 'quiz_question',
    question: 'How long should you scrub your hands?',
    options: ['5 seconds', 'At least 20 seconds', '1 minute'],
    correct_index: 1,
    countdown_s: 4,
    narration: 'Quick quiz: how long should you scrub your hands?',
    duration_s: 8,
  },
  quiz_answer: {
    template: 'quiz_answer',
    question: 'How long should you scrub your hands?',
    options: ['5 seconds', 'At least 20 seconds', '1 minute'],
    correct_index: 1,
    explanation: 'Scrub for at least 20 seconds to remove germs.',
    narration: 'The answer is at least twenty seconds.',
    duration_s: 4.5,
  },
  summary: {
    template: 'summary',
    heading: 'Clean hands in 6 steps',
    points: [
      'Wet, soap and scrub for 20 seconds',
      'Rinse under running water',
      'Dry with a single-use towel',
    ],
    narration: 'Remember: wet, soap and scrub, rinse, and dry with a single-use towel.',
    duration_s: 5.5,
  },
  disclaimer: {
    template: 'disclaimer',
    heading: "Follow your doctor's instructions",
    text: 'This video summarises the document you received. It does not replace advice from your care team.',
    narration: "Always follow your doctor's instructions. This video summarises the document you received.",
    duration_s: 5,
  },
};

const ka: Record<Template, Ex> = {
  title_card: {
    template: 'title_card',
    title: 'როგორ დავიბანოთ ხელები',
    subtitle: 'სამზარეულოს ჰიგიენა · 6 ნაბიჯი',
    icon: 'hand-wash',
    narration: 'ამ ვიდეოში ისწავლით, როგორ დაიბანოთ ხელები სწორად.',
    duration_s: 4,
  },
  step_card: {
    template: 'step_card',
    step_no: 1,
    total_steps: 6,
    icon: 'droplets',
    text: 'დაისველეთ ხელები *სუფთა გამდინარე* წყლით',
    narration: 'პირველი ნაბიჯი: დაისველეთ ხელები სუფთა გამდინარე წყლით.',
    duration_s: 4,
  },
  do_dont: {
    template: 'do_dont',
    do_text: 'გაიმშრალეთ ხელები *ერთჯერადი* ხელსახოცით',
    do_icon: 'wind',
    dont_text: 'არასოდეს გაიწმინდოთ ხელები *წინსაფარზე*',
    dont_icon: 'apron',
    narration: 'გაიმშრალეთ ხელები ერთჯერადი ხელსახოცით და არასოდეს გაიწმინდოთ ისინი წინსაფარზე.',
    duration_s: 6,
  },
  checklist: {
    template: 'checklist',
    heading: 'დაწყებამდე',
    items: ['მოიხსენით ბეჭდები და საათი', 'აიკეცეთ სახელოები', 'შეამოწმეთ, არის თუ არა საპონი'],
    narration: 'დაწყებამდე მოიხსენით ბეჭდები და საათი, აიკეცეთ სახელოები და შეამოწმეთ, არის თუ არა საპონი.',
    duration_s: 7,
  },
  warning: {
    template: 'warning',
    heading: 'ცხელმა წყალმა შეიძლება დაგწვათ',
    text: 'შეამოწმეთ წყლის ტემპერატურა, სანამ ხელებს ონკანქვეშ შეუშვერთ.',
    icon: 'flame',
    narration: 'ფრთხილად: ცხელმა წყალმა შეიძლება დაგწვათ. ჯერ ტემპერატურა შეამოწმეთ.',
    duration_s: 5,
  },
  timer: {
    template: 'timer',
    label: 'იხეხეთ მინიმუმ *20 წამი*',
    seconds: 20,
    icon: 'soap',
    narration: 'იხეხეთ ხელების ყველა ზედაპირი მინიმუმ ოცი წამის განმავლობაში.',
    duration_s: 5.5,
  },
  schedule: {
    template: 'schedule',
    heading: 'წამლის მიღების განრიგი',
    rows: [
      { time: '08:00', text: '1 ტაბლეტი საუზმესთან ერთად', icon: 'sun' },
      { time: '20:00', text: '1 ტაბლეტი ვახშმის შემდეგ', icon: 'moon' },
    ],
    narration: 'მიიღეთ ერთი ტაბლეტი საუზმესთან ერთად რვა საათზე და ერთი ვახშმის შემდეგ ოცი საათზე.',
    duration_s: 6.5,
  },
  quiz_question: {
    template: 'quiz_question',
    question: 'რამდენ ხანს უნდა იხეხოთ ხელები?',
    options: ['5 წამი', 'მინიმუმ 20 წამი', '1 წუთი'],
    correct_index: 1,
    countdown_s: 4,
    narration: 'მოკლე ქვიზი: რამდენ ხანს უნდა იხეხოთ ხელები?',
    duration_s: 8,
  },
  quiz_answer: {
    template: 'quiz_answer',
    question: 'რამდენ ხანს უნდა იხეხოთ ხელები?',
    options: ['5 წამი', 'მინიმუმ 20 წამი', '1 წუთი'],
    correct_index: 1,
    explanation: 'იხეხეთ მინიმუმ 20 წამი, რომ მიკრობები მოცილდეს.',
    narration: 'სწორი პასუხია: მინიმუმ ოცი წამი.',
    duration_s: 4.5,
  },
  summary: {
    template: 'summary',
    heading: 'სუფთა ხელები 6 ნაბიჯში',
    points: [
      'დაისველეთ, გაისაპნეთ, იხეხეთ 20 წამი',
      'ჩამოიბანეთ გამდინარე წყლით',
      'გაიმშრალეთ ერთჯერადი ხელსახოცით',
    ],
    narration: 'დაიმახსოვრეთ: დაისველეთ, გაისაპნეთ, იხეხეთ, ჩამოიბანეთ და გაიმშრალეთ ერთჯერადი ხელსახოცით.',
    duration_s: 6.5,
  },
  disclaimer: {
    template: 'disclaimer',
    heading: 'მიჰყევით ექიმის მითითებებს',
    text: 'ეს ვიდეო აჯამებს თქვენთვის გადაცემულ დოკუმენტს. ის არ ცვლის თქვენი ექიმის რჩევას.',
    narration: 'ყოველთვის მიჰყევით ექიმის მითითებებს. ეს ვიდეო აჯამებს თქვენთვის გადაცემულ დოკუმენტს.',
    duration_s: 6,
  },
};

export const GALLERY: Record<Lang, Record<Template, Ex>> = { en, ka };
export const TEMPLATES = Object.keys(en) as Template[];

/** Composition id (Remotion ids allow only letters, digits and "-"). */
export const galleryId = (template: Template, lang: Lang): string =>
  `Gallery-${template.replace(/_/g, '-')}-${lang}`;

export const galleryScene = (lang: Lang, template: Template): Scene =>
  ({
    ...GALLERY[lang][template],
    id: `${template.replace(/_/g, '-')}-${lang}`,
    evidence: [],
    audio: null,
  }) as Scene;

/** A one-scene spec, for previewing a single template. */
export const gallerySpec = (lang: Lang, template: Template): VideoSpec => ({
  version: 1,
  title: 'Gallery',
  lang,
  source_lang: 'en',
  audience: template === 'disclaimer' || template === 'schedule' ? 'patient' : 'workplace',
  voice: 'Kore',
  theme: 'default',
  target_sec: 30,
  scenes: [galleryScene(lang, template)],
  sources: [],
});

/** All templates back to back, for a full preview of the look in one language. */
export const galleryReel = (lang: Lang): VideoSpec => ({
  ...gallerySpec(lang, 'title_card'),
  title: lang === 'en' ? 'Template reel' : 'შაბლონები',
  audience: 'patient',
  scenes: TEMPLATES.map((t) => galleryScene(lang, t)),
  target_sec: TEMPLATES.reduce((n, t) => n + GALLERY[lang][t].duration_s, 0),
});
