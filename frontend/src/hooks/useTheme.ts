import { useCallback, useEffect, useState } from 'react';
import { readStored, writeStored } from '../utils/storage';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'theme';

function initialTheme(): Theme {
  const saved = readStored(STORAGE_KEY);
  if (saved === 'light' || saved === 'dark') return saved;
  // no explicit choice yet: follow the OS
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Theme state, persisted per browser and applied as a class on <html>
 *  (Tailwind's darkMode: 'class'). */
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.documentElement.style.colorScheme = theme;
    writeStored(STORAGE_KEY, theme);
  }, [theme]);

  // keep following the OS until the user picks a side
  useEffect(() => {
    if (readStored(STORAGE_KEY)) return;
    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e: MediaQueryListEvent) => setTheme(e.matches ? 'dark' : 'light');
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  const toggle = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), []);
  return { theme, setTheme, toggle };
}
