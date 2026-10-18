/**
 * Pictograms the bundled set lacks, drawn in the same 24x24, 2px-stroke, round-cap style so they
 * sit next to Lucide icons without looking foreign. Our own artwork (project licence).
 */
import React from 'react';

export type IconProps = { size?: number; color?: string; strokeWidth?: number };

const Svg: React.FC<IconProps & { children: React.ReactNode }> = ({
  size = 24,
  color = 'currentColor',
  strokeWidth = 2,
  children,
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke={color}
    strokeWidth={strokeWidth}
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    {children}
  </svg>
);

export const Gloves: React.FC<IconProps> = (p) => (
  <Svg {...p}>
    <path d="M7.5 17.5 5 12.6a1.6 1.6 0 0 1 2.7-1.7L9 12.5V4.6a1.5 1.5 0 0 1 3 0V11V3.6a1.5 1.5 0 0 1 3 0V11V5.1a1.5 1.5 0 0 1 3 0v8.4c0 1.6-.5 2.9-1.5 4" />
    <rect x="7" y="17.5" width="10" height="4" rx="1" />
  </Svg>
);

export const FaceMask: React.FC<IconProps> = (p) => (
  <Svg {...p}>
    <path d="M5 9c2-1.3 4.4-2 7-2s5 .7 7 2v4.2c0 3-3.3 5.3-7 5.3s-7-2.3-7-5.3z" />
    <path d="M5 10H3.5a1.5 1.5 0 0 0 0 3H5" />
    <path d="M19 10h1.5a1.5 1.5 0 0 1 0 3H19" />
    <path d="M8.5 11h7" />
    <path d="M8.5 14h7" />
  </Svg>
);

export const HandWash: React.FC<IconProps> = (p) => (
  <Svg {...p}>
    <path d="M12 2.5c1.1 1.6 2 2.7 2 3.7a2 2 0 0 1-4 0c0-1 .9-2.1 2-3.7" />
    <path d="M7 6.5c.6.9 1.1 1.5 1.1 2.1a1.1 1.1 0 0 1-2.2 0c0-.6.5-1.2 1.1-2.1" />
    <path d="M17 6.5c.6.9 1.1 1.5 1.1 2.1a1.1 1.1 0 0 1-2.2 0c0-.6.5-1.2 1.1-2.1" />
    <path d="M2.5 15c2.2-1.2 4.5-1.2 6.5 0l3 1.8 3-1.8c2-1.2 4.3-1.2 6.5 0" />
    <path d="M2.5 19.5c3.2 1.6 6.3 1.6 9.5 0 3.2 1.6 6.3 1.6 9.5 0" />
  </Svg>
);

export const Apron: React.FC<IconProps> = (p) => (
  <Svg {...p}>
    <path d="M9 2.5a3 3 0 0 0 6 0" />
    <path d="M7.5 8h9l1 13.5h-11z" />
    <path d="M7.5 10.5H3.5" />
    <path d="M16.5 10.5h4" />
    <path d="M10 14h4v3h-4z" />
  </Svg>
);

export const CUSTOM_ICONS: Record<string, React.FC<IconProps>> = {
  gloves: Gloves,
  'face-mask': FaceMask,
  'hand-wash': HandWash,
  apron: Apron,
};
