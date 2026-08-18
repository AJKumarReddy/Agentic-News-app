/**
 * Fold a transcript into whatever is already in the box.
 *
 * Appending rather than replacing: someone who typed half a question and then
 * spoke the rest meant to add to it, and silently discarding typed text is the
 * one outcome with no undo. Dictating twice in a row appends twice, which is
 * how a person expects speaking to behave.
 */
export function appendTranscript(current: string, incoming: string): string {
  const addition = incoming.trim();
  if (!addition) return current;
  const base = current.trimEnd();
  return base ? `${base} ${addition}` : addition;
}
