/**
 * The icon catalog: the LLM may only pick names listed in src/catalog/icons.json. Each entry maps
 * to a Lucide icon (MIT/ISC) or one of our custom pictograms.
 */
import catalog from '../catalog/icons.json';

export type IconEntry = {
  name: string;
  lucide?: string;
  custom?: boolean;
  tags: { en: string[]; ka: string[] };
};

export const ICONS: IconEntry[] = catalog.icons;
export const ICON_NAMES: string[] = ICONS.map((i) => i.name);
const BY_NAME = new Map(ICONS.map((i) => [i.name, i]));

export const hasIcon = (name: string): boolean => BY_NAME.has(name);
export const iconEntry = (name: string): IconEntry | undefined => BY_NAME.get(name);

/** Catalog names whose name or tags (any language) contain the query, best matches first. */
export const searchIcons = (query: string): string[] => {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  const scored: [number, string][] = [];
  for (const i of ICONS) {
    const tags = [...i.tags.en, ...i.tags.ka].map((t) => t.toLowerCase());
    const score =
      i.name === q ? 3 : tags.includes(q) ? 2 : tags.some((t) => t.includes(q)) || i.name.includes(q) ? 1 : 0;
    if (score) scored.push([score, i.name]);
  }
  return scored.sort((a, b) => b[0] - a[0]).map(([, n]) => n);
};
