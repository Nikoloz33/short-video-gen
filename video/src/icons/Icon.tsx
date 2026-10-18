import { icons as lucide } from 'lucide-react';
import React from 'react';
import { iconEntry } from './catalog';
import { CUSTOM_ICONS, type IconProps } from './custom';

/** Renders a catalog icon by name. Unknown names throw: validation should have caught them. */
export const Icon: React.FC<IconProps & { name: string }> = ({ name, ...props }) => {
  const entry = iconEntry(name);
  if (!entry) throw new Error(`unknown icon "${name}" (not in src/catalog/icons.json)`);
  if (entry.custom) {
    const Custom = CUSTOM_ICONS[name];
    if (!Custom) throw new Error(`custom icon "${name}" has no component`);
    return <Custom {...props} />;
  }
  const Lucide = lucide[entry.lucide as keyof typeof lucide];
  if (!Lucide) throw new Error(`icon "${name}" maps to missing lucide icon "${entry.lucide}"`);
  return <Lucide size={props.size} color={props.color} strokeWidth={props.strokeWidth} />;
};
