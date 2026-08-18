import type { VoicePref } from '../hooks/useVoice';
import SettingRow from './SettingRow';
import VoiceIcon from './VoiceIcon';

// "Always", not a bare On/Off, because this is a standing preference rather
// than a play button: it decides whether every future answer is spoken, and
// the per-answer control in the chat stays available either way.
const OPTIONS: { value: VoicePref; label: string }[] = [
  { value: 'off', label: 'Always off' },
  { value: 'on', label: 'Always on' },
];

/**
 * Whether answers are read aloud. Deliberately the same segmented control as
 * ThemeToggle and sitting directly beneath it — a second preference in the
 * place the first one taught the reader to look.
 *
 * The heading icon doubles as a state light: it takes the speaking silhouette
 * and the accent colour while the preference is on, so the row still reads at
 * a glance once the eye has stopped reading the words.
 */
export default function VoiceToggle({
  voice,
  onSelect,
}: {
  voice: VoicePref;
  onSelect: (voice: VoicePref) => void;
}) {
  const on = voice === 'on';
  return (
    <SettingRow
      icon={
        <VoiceIcon
          state={on ? 'speaking' : 'idle'}
          className={`h-3.5 w-3.5 ${on ? 'text-accent-300' : 'text-white/40'}`}
        />
      }
      label="Read answers aloud"
    >
      <div
        role="radiogroup"
        aria-label="Read answers aloud"
        className="flex gap-1 rounded-md bg-white/[0.05] p-0.5"
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
    </SettingRow>
  );
}
