import { describe, expect, it } from 'vitest';
import { DEFAULT_THEME, resolveTheme } from './theme';

describe('theme', () => {
  it('returns the default theme unchanged', () => {
    expect(resolveTheme()).toEqual(DEFAULT_THEME);
  });

  it('applies tenant overrides deeply without touching other keys', () => {
    const t = resolveTheme('clinic');
    expect(t.colors.primary).toBe('#00796B');
    expect(t.colors.bad).toBe(DEFAULT_THEME.colors.bad);
    expect(t.size).toEqual(DEFAULT_THEME.size);
  });

  it('applies an explicit override last', () => {
    const t = resolveTheme('kitchen', { colors: { primary: '#000000' }, radius: 0 });
    expect(t.colors.primary).toBe('#000000');
    expect(t.colors.bg).toBe('#FFF5EC');
    expect(t.radius).toBe(0);
  });

  it('falls back to default for unknown tenants', () => {
    expect(resolveTheme('nope').colors.primary).toBe(DEFAULT_THEME.colors.primary);
  });

  it('keeps the caption band below the content and inside the frame', () => {
    const { safe } = DEFAULT_THEME;
    expect(safe.contentBottom).toBeLessThan(safe.captionTop);
    expect(safe.captionBottom).toBeLessThanOrEqual(1920 * 0.82);
  });
});
