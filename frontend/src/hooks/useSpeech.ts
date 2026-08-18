import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchSpeech } from '../services/api';

/**
 * Playback of one answer at a time.
 *
 * `speak` is deliberately stable across renders — MessageBubble is memoised so
 * that earlier messages do not re-parse their markdown on every token batch,
 * and a callback whose identity changed each render would defeat that. The
 * current message is therefore tracked in a ref as well as in state: state
 * drives the icon, the ref keeps the callback's dependency list empty.
 */
export function useSpeech() {
  const [speakingId, setSpeakingId] = useState<number | null>(null);
  const [loadingId, setLoadingId] = useState<number | null>(null);
  const [errorId, setErrorId] = useState<number | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const speakingRef = useRef<number | null>(null);
  // synchronous re-entry guard: state updates are async, so two fast clicks
  // would both start a request
  const busyRef = useRef(false);

  const release = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    release();
    speakingRef.current = null;
    busyRef.current = false;
    setSpeakingId(null);
    setLoadingId(null);
  }, [release]);

  const speak = useCallback(
    async (conversationId: string, messageId: number) => {
      // clicking the icon of the answer that is talking stops it
      if (speakingRef.current === messageId) {
        stop();
        return;
      }
      if (busyRef.current) return;

      stop();
      busyRef.current = true;
      setErrorId(null);
      setLoadingId(messageId);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const blob = await fetchSpeech(conversationId, messageId, controller.signal);
        if (controller.signal.aborted) return;
        if (!blob) {
          // nothing speakable in this answer — not a failure, just silence
          setLoadingId(null);
          busyRef.current = false;
          return;
        }

        const url = URL.createObjectURL(blob);
        urlRef.current = url;
        const audio = audioRef.current ?? new Audio();
        audioRef.current = audio;
        audio.src = url;
        audio.onended = () => {
          speakingRef.current = null;
          setSpeakingId(null);
        };

        await audio.play();
        speakingRef.current = messageId;
        setSpeakingId(messageId);
      } catch {
        if (!controller.signal.aborted) {
          // covers both a failed request and a play() the browser refused
          // because no gesture preceded it — either way, back to idle
          setErrorId(messageId);
          release();
        }
      } finally {
        setLoadingId(null);
        busyRef.current = false;
      }
    },
    [release, stop],
  );

  // A route change unmounts the chat page; an answer still talking over the
  // search results is a bug, not a feature.
  useEffect(() => stop, [stop]);

  return { speakingId, loadingId, errorId, speak, stop };
}
