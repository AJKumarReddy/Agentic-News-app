import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ThemeToggle from './ThemeToggle';

describe('ThemeToggle', () => {
  it('marks the active theme and only that one', () => {
    render(<ThemeToggle theme="dark" onSelect={() => {}} />);
    expect(screen.getByRole('radio', { name: /dark/i })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('radio', { name: /light/i })).toHaveAttribute('aria-checked', 'false');
  });

  it('selects the theme that was clicked, not merely the opposite', () => {
    const onSelect = vi.fn();
    render(<ThemeToggle theme="dark" onSelect={onSelect} />);
    screen.getByRole('radio', { name: /dark/i }).click();
    // clicking the already-active option must not flip to light
    expect(onSelect).toHaveBeenCalledWith('dark');
  });

  it('names the setting, so "Light / Dark" is not the only thing on screen', () => {
    render(<ThemeToggle theme="light" onSelect={() => {}} />);
    expect(screen.getByText('Theme')).toBeInTheDocument();
  });

  it('exposes both options as a labelled radio group', () => {
    render(<ThemeToggle theme="light" onSelect={() => {}} />);
    expect(screen.getByRole('radiogroup', { name: /colour theme/i })).toBeInTheDocument();
    expect(screen.getAllByRole('radio')).toHaveLength(2);
  });
});
