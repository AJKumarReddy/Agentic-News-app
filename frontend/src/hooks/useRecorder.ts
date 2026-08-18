import { useCallback, useEffect, useRef, useState } from 'react';
import { transcribeAudio } from '../services/api';
import type { RecordingState } from '../types';

/** Containers MediaRecorder actually produces, best first. Chrome and Firefox
 *  give WebM/Opus; Safari has only ever supported MP4. The list is probed
 *  rather than assumed because an unsupported string makes the constructor
 *  throw. */
const CANDIDATE_TYPES = [
  'audio/webm;codecs=opus',
  'audio/webm',
  'audio/mp4',
  'audio/ogg;codecs=opus',
];

export function pickMimeType(): string {
  if (typeof MediaRecorder === 'undefined' || !MediaRecorder.isTypeSupported) return '';
  return CANDIDATE_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? '';
}

/** Whether this browser can record at all.
 *
 * `isSecureContext` matters as much as the APIs: getUserMedia is unavailable
 * over plain HTTP, so a deployment reached without TLS must not render a
 * button that can only fail. localhost counts as secure, which is why it works
 * in development. */
export function recordingSupported(): boolean {
  if (typeof window === 'undefined') return false;
  if (!window.isSecureContext) return false;
  if (typeof MediaRecorder === 'undefined') return false;
  return Boolean(navigator.mediaDevices?.getUserMedia);
}

function describe(error: unknown): string {
  const name = (error as { name?: string } | null)?.name;
  if (name === 'NotAllowedError' || name === 'SecurityError') {
    return 'Microphone access was blocked. Allow it in your browser settings to ask out loud.';
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return 'No microphone was found.';
  }
  return 'Could not record audio. Please try again.';
}

/**
 * One spoken question: record, upload, hand back text.
 *
 * The hook owns the microphone, so it also owns letting go of it. Every exit —
 * stop, failure, unmount — runs through `release`, because a track left live
 * keeps the browser's recording indicator lit, and to the reader that reads as
 * the page still listening after they thought they had finished.
 */
export function useRecorder({
  maxSeconds = 60,
  onTranscript,
}: {
  maxSeconds?: number;
  onTranscript: (text: string) => void;
}) {
  const [state, setState] = useState<RecordingState>('idle');
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const stopAtRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // set on unmount: a request in flight must not call setState afterwards, and
  // must not deliver a transcript to a page that has moved on
  const goneRef = useRef(false);
  // the latest callback without making `start` unstable
  const onTranscriptRef = useRef(onTranscript);
  onTranscriptRef.current = onTranscript;

  const release = useCallback(() => {
    if (tickRef.current) clearInterval(tickRef.current);
    if (stopAtRef.current) clearTimeout(stopAtRef.current);
    tickRef.current = null;
    stopAtRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    recorderRef.current = null;
  }, []);

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      // onstop does the upload; tracks are released there
      recorder.stop();
    } else {
      release();
      setState('idle');
    }
  }, [release]);

  const start = useCallback(async () => {
    if (recorderRef.current) return;
    setError(null);
    setSeconds(0);

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (cause) {
      if (goneRef.current) return;
      setError(describe(cause));
      setState('error');
      return;
    }

    // unmounted while the permission prompt was open: let the microphone go
    // rather than leaving a live track behind a page nobody is on
    if (goneRef.current) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }

    streamRef.current = stream;
    chunksRef.current = [];
    const mimeType = pickMimeType();
    const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    recorderRef.current = recorder;

    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
    };

    recorder.onstop = async () => {
      const chunks = chunksRef.current;
      chunksRef.current = [];
      // the microphone is no longer needed the moment recording ends — do not
      // hold it for the length of the upload
      release();
      if (goneRef.current) return;

      const audio = new Blob(chunks, { type: mimeType || 'audio/webm' });
      if (audio.size === 0) {
        setState('idle');
        return;
      }

      setState('transcribing');
      try {
        const text = await transcribeAudio(audio);
        if (goneRef.current) return;
        // null means the recording held no speech — nothing to add, and not
        // an error worth showing
        if (text) onTranscriptRef.current(text);
        setState('idle');
      } catch {
        if (goneRef.current) return;
        setError('Could not turn that recording into text. Please try again.');
        setState('error');
      }
    };

    recorder.start();
    setState('recording');
    tickRef.current = setInterval(() => setSeconds((n) => n + 1), 1000);
    // a microphone left open would otherwise run until it hit the upload
    // ceiling and came back as a 413
    stopAtRef.current = setTimeout(stop, maxSeconds * 1000);
  }, [maxSeconds, release, stop]);

  const toggle = useCallback(() => {
    if (state === 'recording') stop();
    else if (state !== 'transcribing') start();
  }, [state, start, stop]);

  useEffect(() => {
    goneRef.current = false;
    return () => {
      goneRef.current = true;
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== 'inactive') recorder.stop();
      release();
    };
  }, [release]);

  return { state, seconds, error, start, stop, toggle };
}
