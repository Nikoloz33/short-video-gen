/** Visual QA still: every catalog icon with its name, plus a Latin + Georgian type sample. */
import React from 'react';
import { AbsoluteFill } from 'remotion';
import { ICONS } from './icons/catalog';
import { Icon } from './icons/Icon';
import { loadBundledFonts } from './theme/fonts';
import { DEFAULT_THEME as T } from './theme/theme';

loadBundledFonts();

export const IconSheet: React.FC = () => (
  <AbsoluteFill
    style={{ background: T.colors.bg, fontFamily: T.font.family, color: T.colors.ink, padding: 40 }}
  >
    <div style={{ fontSize: 44, fontWeight: 700 }}>Wash your hands · დაიბანეთ ხელები · 20 წამი</div>
    <div style={{ fontSize: 30, color: T.colors.muted, marginBottom: 24 }}>
      Noto Sans 400/700 + Noto Sans Georgian — {ICONS.length} icons
    </div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
      {ICONS.map((i) => (
        <div
          key={i.name}
          style={{
            width: 118,
            height: 112,
            background: T.colors.surface,
            borderRadius: 14,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            outline: i.custom ? `3px solid ${T.colors.accent}` : undefined,
          }}
        >
          <Icon name={i.name} size={52} color={T.colors.primary} />
          <div style={{ fontSize: 15, textAlign: 'center' }}>{i.name}</div>
        </div>
      ))}
    </div>
  </AbsoluteFill>
);
