import type { Theme } from '../hooks/useTheme';
import SettingRow from './SettingRow';

const OPTIONS: { value: Theme; label: string; icon: JSX.Element }[] = [
  {
    value: 'light',
    label: 'Light',
    icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    ),
  },
  {
    value: 'dark',
    label: 'Dark',
    icon: (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
      </svg>
    ),
  },
];

// A half-filled disc, the conventional "appearance" mark. Deliberately not a
// sun or a moon: those two already label the options below it, and repeating
// one of them in the heading would read as the current value rather than as
// the name of the setting.
const ThemeMark = (
  <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 3a9 9 0 000 18z" fill="currentColor" stroke="none" />
  </svg>
);

/** Segmented control rather than a sliding switch: each option is a real
 *  flex item, so nothing depends on absolute offsets that drift with font
 *  metrics or zoom. It also shows both states at once. */
export default function ThemeToggle({
  theme,
  onSelect,
}: {
  theme: Theme;
  onSelect: (theme: Theme) => void;
}) {
  return (
    <SettingRow icon={<span className="text-white/40">{ThemeMark}</span>} label="Theme">
      <div
        role="radiogroup"
        aria-label="Colour theme"
        className="flex gap-1 rounded-md bg-white/[0.05] p-0.5"
      >
        {OPTIONS.map((option) => {
          const active = theme === option.value;
          return (
            <button
              key={option.value}
              role="radio"
              aria-checked={active}
              onClick={() => onSelect(option.value)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-1.5 text-[12px] font-medium transition-colors ${
                active
                  ? 'bg-white/[0.12] text-white'
                  : 'text-white/45 hover:bg-white/[0.05] hover:text-white/75'
              }`}
            >
              {option.icon}
              {option.label}
            </button>
          );
        })}
      </div>
    </SettingRow>
  );
}
