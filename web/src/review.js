// Review list helpers. Items: [{passageId,title,source,suspects:[{expected,heard}]}].
/** Remove a dismissed suspect word from every passage; drop passages left with none. Returns a new array. */
export function dismissWord(items, word) {
  return items
    .map((it) => ({ ...it, suspects: it.suspects.filter((s) => s.expected !== word) }))
    .filter((it) => it.suspects.length > 0);
}
export const suspectCount = (items) => items.reduce((n, it) => n + it.suspects.length, 0);
export const fixHref = (word) => `#/pronunciations?word=${encodeURIComponent(word)}`;
