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
  // The browser refused to start audio without a gesture. Distinct from an
  // error: nothing failed, the reader simply has not interacted yet, and the
  // fix is one tap rather than a retry. Shown once — once any playback has
  // succeeded the page has user activation and it cannot recur this session.
  const [autoplayBlocked, setAutoplayBlocked] = useState(false);
  const everPlayedRef = useRef(false);

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
        everPlayedRef.current = true;
        setAutoplayBlocked(false);
        speakingRef.current = messageId;
        setSpeakingId(messageId);
      } catch (error) {
        if (!controller.signal.aborted) {
          // Two different failures used to land here as one. A play() the
          // browser refused for want of a gesture is not a broken answer, and
          // telling the reader "audio unavailable" sent them to retry a button
          // that would fail identically. Autoplay refusal asks for a tap; a
          // genuine failure keeps the error state.
          const refused =
            error instanceof DOMException && error.name === 'NotAllowedError';
          if (refused && !everPlayedRef.current) setAutoplayBlocked(true);
          else setErrorId(messageId);
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

  /** Called from a real click, which carries the activation autoplay lacked. */
  const dismissAutoplayPrompt = useCallback(() => setAutoplayBlocked(false), []);

  return {
    speakingId,
    loadingId,
    errorId,
    autoplayBlocked,
    dismissAutoplayPrompt,
    speak,
    stop,
  };
}
