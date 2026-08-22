import { useCallback, useState } from 'react';
import { readStored, writeStored } from '../utils/storage';

export type VoicePref = 'on' | 'off';

const STORAGE_KEY = 'voice';
const NUDGE_KEY = 'voice-nudged';

// the try/catch and the legacy-key migration both live in utils/storage
const read = readStored;
const write = writeStored;

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
