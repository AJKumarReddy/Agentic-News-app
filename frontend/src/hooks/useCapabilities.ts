import { useEffect, useState } from 'react';
import { getCapabilities } from '../services/api';
import type { Capabilities } from '../types';

/** Nothing until the backend says otherwise. A control that cannot work is
 *  worse than no control, so the answer we assume before the probe lands is
 *  the one that renders nothing. */
const NONE: Capabilities = { tts: false, stt: false };

/**
 * What this deployment can actually do.
 *
 * Owned by App and passed down, rather than called by each feature that cares:
 * playback and voice input both gate on it, and a hook that fetched per caller
 * would put two identical requests on every page load.
 *
 * A failure leaves every flag false — the same shape as a backend that has the
 * feature switched off, which is exactly how it should be treated.
 */
export function useCapabilities(): Capabilities {
  const [capabilities, setCapabilities] = useState<Capabilities>(NONE);

  useEffect(() => {
    let cancelled = false;
    getCapabilities()
      .then((next) => {
        if (cancelled) return;
        // Boolean() rather than a spread: an older backend answers with tts
        // alone, and an absent stt must read as false, not undefined.
        setCapabilities({ tts: Boolean(next?.tts), stt: Boolean(next?.stt) });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  return capabilities;
}
