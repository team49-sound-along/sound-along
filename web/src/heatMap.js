// Shaping for the passage heat-map: which words are shaded, how dark, and what a tap says. Pure; no DOM, no Vue.

export const TOP_WORDS = 5;

/** A word's letters only, lower case ("Laughed." and "laughed" are one word), like the server's own key. */
export const wordKey = (text) => String(text ?? "").toLowerCase().normalize("NFC").replace(/[^\p{L}\p{N}]/gu, "");

/** 0 = not shaded, 1 (light yellow) to 3 (deep yellow): the share of reads that missed the word. */
export function heatLevel(missed, sessions) {
  if (!missed || !sessions) return 0;
  const share = missed / sessions;
  if (share < 0.25) return 1;
  if (share < 0.5) return 2;
  return 3;
}

export const missedText = (missed, sessions) => `Missed by ${missed} of ${sessions} readers`;

/**
 * The passage as paragraphs of words ready to draw. `top` is the set of word keys in the "hard words" list: they get a marker besides the
 * colour, so the meaning never depends on colour alone.
 */
export function annotateTokens(tokens, sessions, top) {
  const paragraphs = [];
  for (const t of tokens) {
    const level = heatLevel(t.missed, sessions);
    const word = { i: t.i, text: t.text, missed: t.missed, level, top: level > 0 && top.has(wordKey(t.text)), title: level > 0 ? missedText(t.missed, sessions) : "" };
    const at = paragraphs.length && paragraphs[paragraphs.length - 1].paragraph === t.paragraph ? paragraphs.length - 1 : -1;
    if (at === -1) paragraphs.push({ paragraph: t.paragraph, words: [word] });
    else paragraphs[at] = { ...paragraphs[at], words: [...paragraphs[at].words, word] };
  }
  return paragraphs.map((p) => p.words);
}

/** "Top 5 hard words": a ranked list, the text alternative to the colours. */
export const topWordRows = (items, n = TOP_WORDS) => (items ?? []).slice(0, n).map((w, k) => ({ word: w.word, text: missedText(w.missed, w.sessions), rank: k + 1 }));
