import { useEffect, useState } from 'react';
import { listSources } from '../services/api';
import type { NewsSourceInfo } from '../types';

/** Publishers this deployment is actually serving.
 *
 *  Named in the UI rather than hard-coded, so the copy cannot drift from the
 *  backend: a source with no API key is skipped, and the sentence naming the
 *  newsrooms would otherwise promise reporting that never arrives.
 */
export function useSources(): NewsSourceInfo[] {
  const [sources, setSources] = useState<NewsSourceInfo[]>([]);
  useEffect(() => {
    listSources()
      .then(setSources)
      .catch(() => setSources([]));
  }, []);
  return sources;
}
