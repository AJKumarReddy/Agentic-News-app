import type { Theme } from '../hooks/useTheme';

export default function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const isDark = theme === 'dark';
  return (
    <button
      onClick={onToggle}
      role="switch"
      aria-checked={isDark}
      aria-label={`Switch to ${isDark ? 'light' : 'dark'} mode`}
      title={`Switch to ${isDark ? 'light' : 'dark'} mode`}
      className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-[13px] font-medium text-white/70 transition-colors hover:bg-white/5 hover:text-white"
    >
      <span className="flex items-center gap-2.5">
        {isDark ? (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
          </svg>
        ) : (
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
          </svg>
        )}
        {isDark ? 'Dark' : 'Light'} mode
      </span>
      <span
        className={`relative h-4 w-7 rounded-full transition-colors ${isDark ? 'bg-accent-500' : 'bg-white/20'}`}
      >
        <span
          className={`absolute top-0.5 h-3 w-3 rounded-full bg-white dark:bg-ink-800 transition-transform ${
            isDark ? 'translate-x-3.5' : 'translate-x-0.5'
          }`}
        />
      </span>
    </button>
  );
}
