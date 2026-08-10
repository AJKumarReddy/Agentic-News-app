import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import RouteBadge from './RouteBadge';

describe('RouteBadge', () => {
  it('labels a newsroom-routed answer', () => {
    render(
      <RouteBadge routing={{ route: 'NEWS', intent: 'LATEST', standalone_question: 'Latest AI news' }} />,
    );
    expect(screen.getByText('Newsrooms')).toBeInTheDocument();
    expect(screen.getByText('latest')).toBeInTheDocument();
  });

  it('labels a web-routed answer distinctly', () => {
    render(<RouteBadge routing={{ route: 'WEB', intent: 'QA', standalone_question: 'how to x' }} />);
    expect(screen.getByText('Web')).toBeInTheDocument();
  });

  it('labels a mixed-source answer', () => {
    render(<RouteBadge routing={{ route: 'BOTH', intent: 'ENTITY', standalone_question: 'q' }} />);
    expect(screen.getByText('News + Web')).toBeInTheDocument();
  });

  it('shows how a terse follow-up was interpreted', () => {
    render(
      <RouteBadge
        routing={{
          route: 'WEB',
          intent: 'QA',
          standalone_question: 'Related news about UK manufacturers facing cyber-attacks',
        }}
      />,
    );
    expect(screen.getByText(/UK manufacturers facing cyber-attacks/)).toBeInTheDocument();
  });
});
