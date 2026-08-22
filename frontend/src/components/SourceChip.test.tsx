import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SourceChip from './SourceChip';

/** The bug this guards: every relayed article carries source_id "thenewsapi",
 *  so a chip keyed on the id painted all of them the same colour while only
 *  the Guardian looked like a publisher. */
describe('SourceChip', () => {
  const classesOf = (testId: string) => screen.getByText(testId).className;

  it('shows the publisher name, not the domain', () => {
    render(<SourceChip sourceId="thenewsapi" name="foxnews.com" />);
    expect(screen.getByText('FOX News')).toBeInTheDocument();
  });

  it('gives different publishers different colours', () => {
    render(
      <>
        <SourceChip sourceId="thenewsapi" name="foxnews.com" />
        <SourceChip sourceId="thenewsapi" name="cbsnews.com" />
        <SourceChip sourceId="thenewsapi" name="nypost.com" />
      </>,
    );
    const colours = new Set([classesOf('FOX News'), classesOf('CBS News'), classesOf('NY Post')]);
    expect(colours.size).toBeGreaterThan(1);
  });

  it('keeps one publisher on the same colour everywhere', () => {
    const { unmount } = render(<SourceChip sourceId="thenewsapi" name="cbsnews.com" />);
    const first = classesOf('CBS News');
    unmount();
    render(<SourceChip sourceId="thenewsapi" name="https://www.cbsnews.com/" />);
    expect(classesOf('CBS News')).toBe(first);
  });

  it('never falls back to an uncoloured chip', () => {
    render(<SourceChip sourceId="thenewsapi" name="some-local-paper.co.uk" />);
    expect(classesOf('Some Local Paper')).toMatch(/bg-\w+-100/);
  });

  it('keeps the first-party sources on their own colours', () => {
    render(
      <>
        <SourceChip sourceId="guardian" name="The Guardian" />
        <SourceChip sourceId="web" name="example.com" />
      </>,
    );
    expect(classesOf('Guardian')).toContain('#0b5394');
    expect(classesOf('Web')).toContain('warm');
  });
});
