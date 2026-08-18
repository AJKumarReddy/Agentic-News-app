import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../services/api', () => ({
  transcribeAudio: vi.fn(async () => 'What did the Fed say?'),
}));

import { transcribeAudio } from '../services/api';
import { recordingSupported, useRecorder } from './useRecorder';

/** Tracks the microphone hands out, so a test can assert every one was
 *  released — a live track keeps the browser's recording indicator lit. */
let tracks: { stop: ReturnType<typeof vi.fn> }[] = [];
let instances: FakeRecorder[] = [];

class FakeRecorder {
  static isTypeSupported = (type: string) => type === 'audio/webm;codecs=opus';
  state: 'inactive' | 'recording' = 'inactive';
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;

  constructor(
    public stream: unknown,
    public options?: { mimeType?: string },
  ) {
    instances.push(this);
  }

  start() {
    this.state = 'recording';
  }

  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['AUDIO']) });
    this.onstop?.();
  }
}

function grantMicrophone() {
  const getUserMedia = vi.fn(async () => {
    const track = { stop: vi.fn() };
    tracks.push(track);
    return { getTracks: () => [track] } as unknown as MediaStream;
  });
  Object.defineProperty(navigator, 'mediaDevices', {
    value: { getUserMedia },
    configurable: true,
  });
  return getUserMedia;
}

function denyMicrophone(name = 'NotAllowedError') {
  Object.defineProperty(navigator, 'mediaDevices', {
    value: {
      getUserMedia: vi.fn(async () => {
        throw Object.assign(new Error('denied'), { name });
      }),
    },
    configurable: true,
  });
}

beforeEach(() => {
  tracks = [];
  instances = [];
  vi.stubGlobal('MediaRecorder', FakeRecorder);
  Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true });
  vi.mocked(transcribeAudio).mockReset();
  vi.mocked(transcribeAudio).mockResolvedValue('What did the Fed say?');
  grantMicrophone();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function mount(onTranscript = vi.fn()) {
  const rendered = renderHook(() => useRecorder({ maxSeconds: 60, onTranscript }));
  return { ...rendered, onTranscript };
}

describe('recordingSupported', () => {
  it('refuses over plain HTTP, where getUserMedia does not exist', () => {
    Object.defineProperty(window, 'isSecureContext', { value: false, configurable: true });
    expect(recordingSupported()).toBe(false);
  });

  it('refuses a browser with no MediaRecorder', () => {
    vi.stubGlobal('MediaRecorder', undefined);
    expect(recordingSupported()).toBe(false);
  });

  it('accepts a secure context with both APIs', () => {
    expect(recordingSupported()).toBe(true);
  });
});

describe('useRecorder', () => {
  it('picks a container the browser actually supports', async () => {
    const { result } = mount();
    await act(async () => result.current.start());
    expect(instances[0].options?.mimeType).toBe('audio/webm;codecs=opus');
  });

  it('records, transcribes, and hands back the text', async () => {
    const { result, onTranscript } = mount();
    await act(async () => result.current.start());
    expect(result.current.state).toBe('recording');

    await act(async () => result.current.stop());
    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith('What did the Fed say?'));
    await waitFor(() => expect(result.current.state).toBe('idle'));
  });

  it('releases the microphone as soon as recording ends, not after the upload', async () => {
    let release!: (text: string) => void;
    vi.mocked(transcribeAudio).mockReturnValue(
      new Promise<string>((resolve) => {
        release = resolve;
      }),
    );

    const { result } = mount();
    await act(async () => result.current.start());
    await act(async () => result.current.stop());

    await waitFor(() => expect(result.current.state).toBe('transcribing'));
    // still uploading, and the indicator is already out
    expect(tracks.every((track) => track.stop.mock.calls.length > 0)).toBe(true);

    await act(async () => release('done'));
  });

  it('releases the microphone when the page goes away mid-recording', async () => {
    const { result, unmount } = mount();
    await act(async () => result.current.start());
    unmount();
    expect(tracks.every((track) => track.stop.mock.calls.length > 0)).toBe(true);
  });

  it('explains a blocked microphone instead of failing silently', async () => {
    denyMicrophone();
    const { result } = mount();
    await act(async () => result.current.start());

    expect(result.current.state).toBe('error');
    expect(result.current.error).toMatch(/blocked/i);
  });

  it('distinguishes no microphone from a refused one', async () => {
    denyMicrophone('NotFoundError');
    const { result } = mount();
    await act(async () => result.current.start());
    expect(result.current.error).toMatch(/no microphone/i);
  });

  it('says so when the recording could not be turned into text', async () => {
    vi.mocked(transcribeAudio).mockRejectedValue(new Error('502'));
    const { result } = mount();
    await act(async () => result.current.start());
    await act(async () => result.current.stop());

    await waitFor(() => expect(result.current.state).toBe('error'));
    expect(result.current.error).toMatch(/could not turn/i);
  });

  it('adds nothing to the box when the recording held no speech', async () => {
    vi.mocked(transcribeAudio).mockResolvedValue(null);
    const { result, onTranscript } = mount();
    await act(async () => result.current.start());
    await act(async () => result.current.stop());

    await waitFor(() => expect(result.current.state).toBe('idle'));
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it('does not start a second recording over a running one', async () => {
    const { result } = mount();
    await act(async () => result.current.start());
    await act(async () => result.current.start());
    expect(instances).toHaveLength(1);
  });

  it('toggle stops what is running and starts what is not', async () => {
    const { result } = mount();
    await act(async () => result.current.toggle());
    expect(result.current.state).toBe('recording');

    await act(async () => result.current.toggle());
    await waitFor(() => expect(result.current.state).toBe('idle'));
  });
});
