/**
 * One brand theme (colours, type scale, safe areas) + per-tenant overrides.
 * Flat, high-contrast "safety card" look; every size is in output pixels at 1080x1920.
 */

export type Theme = {
  name: string;
  colors: {
    bg: string;
    bgAlt: string;
    surface: string;
    ink: string;
    muted: string;
    primary: string;
    primaryInk: string;
    accent: string;
    ok: string;
    okSoft: string;
    bad: string;
    badSoft: string;
    warn: string;
    warnInk: string;
    captionBg: string;
    captionInk: string;
  };
  font: { family: string };
  size: {
    title: number;
    heading: number;
    body: number;
    item: number;
    caption: number;
    small: number;
    stepNo: number;
  };
  lineHeight: number;
  radius: number;
  /** Content stays inside these insets; the caption band sits between `captionTop` and `captionBottom`. */
  safe: { side: number; top: number; contentBottom: number; captionTop: number; captionBottom: number };
};

export const FONT_STACK = "'Noto Sans', 'Noto Sans Georgian', sans-serif";

export const DEFAULT_THEME: Theme = {
  name: 'default',
  colors: {
    bg: '#EEF3F8',
    bgAlt: '#DCE7F2',
    surface: '#FFFFFF',
    ink: '#13212E',
    muted: '#5B6B7B',
    primary: '#1565C0',
    primaryInk: '#FFFFFF',
    accent: '#FFB300',
    ok: '#2E7D32',
    okSoft: '#E3F4E4',
    bad: '#C62828',
    badSoft: '#FDE7E7',
    warn: '#F9A825',
    warnInk: '#1B1B1B',
    captionBg: 'rgba(19, 33, 46, 0.86)',
    captionInk: '#FFFFFF',
  },
  font: { family: FONT_STACK },
  size: { title: 92, heading: 72, body: 60, item: 52, caption: 44, small: 38, stepNo: 120 },
  lineHeight: 1.25,
  radius: 36,
  safe: { side: 80, top: 150, contentBottom: 1330, captionTop: 1360, captionBottom: 1560 },
};

type DeepPartial<T> = { [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K] };
export type ThemeOverride = DeepPartial<Theme>;

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v);

const merge = <T>(base: T, over: unknown): T => {
  if (!isObject(over) || !isObject(base)) return (over === undefined ? base : over) as T;
  const out: Record<string, unknown> = { ...base };
  for (const [k, v] of Object.entries(over)) out[k] = v === undefined ? out[k] : merge(out[k], v);
  return out as T;
};

/** Tenant themes. Add a key here (or pass an override) to brand a customer's videos. */
export const TENANT_THEMES: Record<string, ThemeOverride> = {
  default: {},
  clinic: {
    name: 'clinic',
    colors: { primary: '#00796B', bg: '#EDF6F5', bgAlt: '#D5EBE8', accent: '#26A69A' },
  },
  kitchen: {
    name: 'kitchen',
    colors: { primary: '#E65100', bg: '#FFF5EC', bgAlt: '#FFE3CC', accent: '#FFB300' },
  },
};

export const resolveTheme = (name = 'default', override?: ThemeOverride): Theme =>
  merge(merge(DEFAULT_THEME, TENANT_THEMES[name] ?? {}), override ?? {});
