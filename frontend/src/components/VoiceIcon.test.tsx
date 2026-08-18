import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import VoiceIcon from './VoiceIcon';

function bars(container: HTMLElement) {
  return Array.from(container.querySelectorAll('rect'));
}

describe('VoiceIcon', () => {
  it('holds still when idle', () => {
    const { container } = render(<VoiceIcon state="idle" />);
    const rects = bars(container);
    expect(rects).toHaveLength(3);
    expect(rects.every((r) => r.getAttribute('class') === '')).toBe(true);
    // resting silhouette is uneven, so it reads as an equalizer at a glance
    const transforms = rects.map((r) => r.style.transform);
    expect(new Set(transforms).size).toBe(3);
  });

  it('animates while speaking', () => {
    const { container } = render(<VoiceIcon state="speaking" />);
    for (const rect of bars(container)) {
      expect(rect.getAttribute('class')).toContain('animate-equalize');
      // the animation owns the transform; no inline scale competes with it
      expect(rect.style.transform).toBe('');
    }
  });

  it('pulses while loading', () => {
    const { container } = render(<VoiceIcon state="loading" />);
    expect(bars(container)[0].getAttribute('class')).toContain('animate-pulse');
  });

  it('opts out of motion for readers who asked to', () => {
    const { container } = render(<VoiceIcon state="speaking" />);
    expect(bars(container)[0].getAttribute('class')).toContain('motion-reduce:animate-none');
  });

  it('staggers the bars so they do not move as one block', () => {
    const { container } = render(<VoiceIcon state="speaking" />);
    const delays = bars(container).map((r) => r.style.animationDelay);
    expect(new Set(delays).size).toBe(3);
  });
});
