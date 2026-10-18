import { icons as lucide } from 'lucide-react';
import { describe, expect, it } from 'vitest';
import { CUSTOM_ICONS } from './custom';
import { ICONS, ICON_NAMES, hasIcon, searchIcons } from './catalog';

describe('icon catalog', () => {
  it('has unique kebab-case names', () => {
    expect(new Set(ICON_NAMES).size).toBe(ICON_NAMES.length);
    for (const n of ICON_NAMES) expect(n).toMatch(/^[a-z0-9]+(-[a-z0-9]+)*$/);
    expect(ICON_NAMES.length).toBeGreaterThanOrEqual(120);
  });

  it('every entry resolves to exactly one real icon', () => {
    for (const i of ICONS) {
      if (i.custom) {
        expect(i.lucide, i.name).toBeUndefined();
        expect(CUSTOM_ICONS[i.name], i.name).toBeDefined();
      } else {
        expect(lucide[i.lucide as keyof typeof lucide], `${i.name} -> ${i.lucide}`).toBeDefined();
      }
    }
  });

  it('every entry has English and Georgian tags', () => {
    for (const i of ICONS) {
      expect(i.tags.en.length, i.name).toBeGreaterThan(0);
      expect(i.tags.ka.length, i.name).toBeGreaterThan(0);
      for (const t of i.tags.ka) expect(t, i.name).toMatch(/[ა-ჿ]/);
    }
  });

  it('looks up and searches in both languages', () => {
    expect(hasIcon('gloves')).toBe(true);
    expect(hasIcon('glove')).toBe(false);
    expect(searchIcons('gloves')[0]).toBe('gloves');
    expect(searchIcons('ხელთათმანი')).toContain('gloves');
    expect(searchIcons('water')).toContain('droplets');
    expect(searchIcons('')).toEqual([]);
  });
});
