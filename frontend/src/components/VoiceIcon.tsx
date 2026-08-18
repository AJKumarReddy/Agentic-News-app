import type { SpeechState } from '../types';

// Resting heights differ per bar so the idle icon reads as an equalizer at a
// glance rather than as three identical ticks.
const BARS = [
  { x: 2.25, rest: 0.45, delay: '0ms' },
  { x: 6.75, rest: 0.95, delay: '160ms' },
  { x: 11.25, rest: 0.65, delay: '320ms' },
];

/**
 * Three bars carrying playback state.
 *
 * Speaking animates; loading pulses; idle and error hold still and differ only
 * in colour, which the caller supplies through currentColor. Under
 * prefers-reduced-motion nothing moves and colour carries the state alone.
 */
export default function VoiceIcon({
  state = 'idle',
  className = '',
}: {
  state?: SpeechState;
  className?: string;
}) {
  const animation =
    state === 'speaking'
      ? 'animate-equalize motion-reduce:animate-none'
      : state === 'loading'
        ? 'animate-pulse motion-reduce:animate-none'
        : '';

  return (
    <svg viewBox="0 0 16 16" className={className} fill="currentColor" aria-hidden="true">
      {BARS.map((bar) => (
        <rect
          key={bar.x}
          x={bar.x}
          y={1.5}
          width={2.5}
          height={13}
          rx={1.25}
          className={animation}
          style={{
            transformBox: 'fill-box',
            transformOrigin: 'center',
            // the animation overrides this while speaking; it is the resting
            // silhouette everywhere else
            transform: state === 'speaking' ? undefined : `scaleY(${bar.rest})`,
            animationDelay: bar.delay,
          }}
        />
      ))}
    </svg>
  );
}
