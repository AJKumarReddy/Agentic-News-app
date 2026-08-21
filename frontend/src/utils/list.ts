/** Join names the way a sentence does: "A", "A and B", "A, B and C".
 *
 *  `join(' and ')` reads fine for two and falls apart at three — "The Guardian
 *  and The New York Times and TheNewsAPI". Source lists are configuration, so
 *  the count changes whenever a publisher is added or a key is missing.
 */
export function joinNames(names: string[]): string {
  if (names.length <= 1) return names[0] ?? '';
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}
