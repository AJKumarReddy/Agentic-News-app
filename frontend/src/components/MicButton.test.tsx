import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import MicButton from './MicButton';
import type { RecordingState } from '../types';

describe('MicButton', () => {
  it.each<[RecordingState, string]>([
    ['idle', 'Ask by voice'],
    ['recording', 'Stop recording'],
    ['transcribing', 'Turning your recording into text'],
  ])('names what it does in the %s state', (state, name) => {
    render(<MicButton state={state} seconds={0} onToggle={() => {}} />);
    expect(screen.getByRole('button', { name })).toBeInTheDocument();
  });

  it('shows the running time, the one thing a mic glyph cannot say', () => {
    render(<MicButton state="recording" seconds={7} onToggle={() => {}} />);
    expect(screen.getByText('0:07')).toBeInTheDocument();
  });

  it('rolls the clock past a minute', () => {
    render(<MicButton state="recording" seconds={75} onToggle={() => {}} />);
    expect(screen.getByText('1:15')).toBeInTheDocument();
  });

  it('cannot be pressed while the recording is being transcribed', () => {
    const onToggle = vi.fn();
    render(<MicButton state="transcribing" seconds={0} onToggle={onToggle} />);
    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
    button.click();
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('toggles when pressed', () => {
    const onToggle = vi.fn();
    render(<MicButton state="idle" seconds={0} onToggle={onToggle} />);
    screen.getByRole('button', { name: 'Ask by voice' }).click();
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('still offers another attempt after a failure', () => {
    render(<MicButton state="error" seconds={0} onToggle={() => {}} />);
    expect(screen.getByRole('button', { name: 'Ask by voice' })).toBeEnabled();
  });

  it('never submits the composer it sits inside', () => {
    // a bare <button> in a form defaults to type=submit, which would send the
    // half-written question the moment the reader reached for the microphone
    render(<MicButton state="idle" seconds={0} onToggle={() => {}} />);
    expect(screen.getByRole('button')).toHaveAttribute('type', 'button');
  });
});
