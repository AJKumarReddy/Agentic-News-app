import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import VoiceToggle from './VoiceToggle';

describe('VoiceToggle', () => {
  it('names the setting, so "Off / On" is not the only thing on screen', () => {
    render(<VoiceToggle voice="off" onSelect={() => {}} />);
    expect(screen.getByText('Read answers aloud')).toBeInTheDocument();
  });

  it('says the choice is a standing one, not a play button', () => {
    render(<VoiceToggle voice="off" onSelect={() => {}} />);
    expect(screen.getByRole('radio', { name: 'Always off' })).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Always on' })).toBeInTheDocument();
  });

  it('marks the active preference and only that one', () => {
    render(<VoiceToggle voice="on" onSelect={() => {}} />);
    expect(screen.getByRole('radio', { name: 'Always on' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByRole('radio', { name: 'Always off' })).toHaveAttribute(
      'aria-checked',
      'false',
    );
  });

  it('selects the option that was clicked rather than toggling', () => {
    const onSelect = vi.fn();
    render(<VoiceToggle voice="on" onSelect={onSelect} />);
    screen.getByRole('radio', { name: 'Always on' }).click();
    expect(onSelect).toHaveBeenCalledWith('on');
  });

  it('exposes the options as one labelled radio group', () => {
    render(<VoiceToggle voice="off" onSelect={() => {}} />);
    expect(screen.getByRole('radiogroup', { name: /read answers aloud/i })).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(2);
  });

  it('does not announce the heading twice, once loose and once as the group', () => {
    // the heading repeats the group's own label purely for sighted readers
    const { container } = render(<VoiceToggle voice="off" onSelect={() => {}} />);
    expect(container.querySelector('[aria-hidden="true"]')?.textContent).toContain(
      'Read answers aloud',
    );
  });
});
