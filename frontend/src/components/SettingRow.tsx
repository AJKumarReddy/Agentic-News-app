import type { ReactNode } from 'react';

/**
 * One named preference: an icon and its name above the control that changes it.
 *
 * The controls underneath are segmented buttons reading "Light / Dark" and
 * "Off / On" — words that say what the *values* are but never what is being
 * set. The name has to sit outside the control for that reason.
 *
 * Marked aria-hidden because the control below already carries the same name
 * as its group label; without this a screen reader announces the name twice,
 * once as loose text and once as the group.
 */
export default function SettingRow({
  icon,
  label,
  children,
}: {
  icon: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <div>
      <div aria-hidden="true" className="mb-1.5 flex items-center gap-2 px-1">
        <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">{icon}</span>
        <span className="text-[11px] font-medium tracking-[0.01em] text-white/60">{label}</span>
      </div>
      {children}
    </div>
  );
}
