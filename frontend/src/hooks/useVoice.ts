import { useCallback, useState } from 'react';

export type VoicePref = 'on' | 'off';

const STORAGE_KEY = 'news-ai-voice';
const NUDGE_KEY = 'news-ai-voice-nudged';

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    // private-mode Safari throws on access; a preference is never worth a crash
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // the choice still applies for this session, it just will not survive
  }
}

function initialVoice(): VoicePref {
  return read(STORAGE_KEY) === 'on' ? 'on' : 'off';
}

/**
 * Whether answers are read aloud, persisted per browser.
 *
 * Mirrors useTheme: a lazy read of localStorage, a write on change. The one
 * difference is that theme falls back to an OS signal when unset and voice has
 * none, so unset simply means off — nobody should be spoken to unasked.
 *
 * `available` is passed in rather than probed here. A deployment with no
 * OpenAI key or with TTS switched off should not render a control that cannot
 * work — but voice input gates on the same request, so App fetches the
 * capabilities once and hands each feature the flag it cares about.
 */
export function useVoice(available: boolean) {
  const [voice, setVoiceState] = useState<VoicePref>(initialVoice);
  // the suggestion is answered by choosing either way, not only by accepting
  const [nudged, setNudged] = useState(
    () => read(NUDGE_KEY) !== null || read(STORAGE_KEY) !== null,
  );

  const setVoice = useCallback((next: VoicePref) => {
    write(STORAGE_KEY, next);
    write(NUDGE_KEY, '1');
    setVoiceState(next);
    setNudged(true);
  }, []);

  const dismissNudge = useCallback(() => {
    write(NUDGE_KEY, '1');
    setNudged(true);
  }, []);

  return { voice, setVoice, available, nudged, dismissNudge };
}
