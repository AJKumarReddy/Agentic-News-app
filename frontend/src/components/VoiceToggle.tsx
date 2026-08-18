import type { VoicePref } from '../hooks/useVoice';
import VoiceIcon from './VoiceIcon';

const OPTIONS: { value: VoicePref; label: string }[] = [
  { value: 'off', label: 'Off' },
  { value: 'on', label: 'On' },
];

/**
 * Whether answers are read aloud. Deliberately the same segmented control as
 * ThemeToggle and sitting directly beneath it — a second preference in the
 * place the first one taught the reader to look.
 */
export default function VoiceToggle({
  voice,
  onSelect,
}: {
  voice: VoicePref;
  onSelect: (voice: VoicePref) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <VoiceIcon
        state={voice === 'on' ? 'speaking' : 'idle'}
        className={`h-3.5 w-3.5 shrink-0 ${voice === 'on' ? 'text-accent-300' : 'text-white/30'}`}
      />
      <div
        role="radiogroup"
        aria-label="Read answers aloud"
        className="flex flex-1 gap-1 rounded-md bg-white/[0.05] p-0.5"
      >
        {OPTIONS.map((option) => {
          const active = voice === option.value;
          return (
            <button
              key={option.value}
              role="radio"
              aria-checked={active}
              onClick={() => onSelect(option.value)}
              className={`flex flex-1 items-center justify-center rounded px-2 py-1.5 text-[12px] font-medium transition-colors ${
                active
                  ? 'bg-white/[0.12] text-white'
                  : 'text-white/45 hover:bg-white/[0.05] hover:text-white/75'
              }`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
