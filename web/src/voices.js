// Voice variants: a passage can have an AI-voice version and a human-narrated version of the same text.
// The API exposes them as two passages linked by `pairId`; the UI shows them as one card with a voice toggle.

export const isHuman = (passage) => passage?.engine === "human";

export const voiceLabel = (engine) => (engine === "human" ? "ReadWorks recording" : "Read-aloud voice");

/** One entry per text. Hides a human variant when its AI pair is present (recorded as `humanId`) and a translation when its source is present
 *  (the source records the languages as `translationLangs`). */
export function groupVariants(passages) {
  const ids = new Set(passages.map((p) => p.id));
  const humanByAi = new Map(passages.filter((p) => isHuman(p) && p.pairId && ids.has(p.pairId)).map((p) => [p.pairId, p.id]));
  const hidden = (p) => (isHuman(p) && p.pairId && ids.has(p.pairId)) || (p.translationOf && ids.has(p.translationOf));
  return passages
    .filter((p) => !hidden(p))
    .map((p) => {
      const langs = Object.entries(p.translations ?? {}).filter(([, tid]) => ids.has(tid)).map(([lang]) => lang);
      return { ...p, ...(humanByAi.has(p.id) ? { humanId: humanByAi.get(p.id) } : {}), ...(langs.length ? { translationLangs: langs } : {}) };
    });
}

/** Which passage id "Read" opens: the human narration when one exists (ReadWorks' best audio), else the passage. */
export const readTarget = (passage) => passage.humanId ?? passage.id;

/** Position to resume at after switching voice: a valid word index from the route query, else null. */
export function resumeIndex(query, wordCount) {
  const at = Number(query?.at);
  return Number.isInteger(at) && at >= 0 && at < wordCount ? at : null;
}

/** The other language of this text, from the link in its timing document, or null. `map` is the sentence map for the direction. */
export function languageSwitch(timing) {
  const forward = Object.entries(timing?.translations ?? {}).find(([, t]) => t?.id && Array.isArray(t.sentenceMap));
  if (forward) return { lang: forward[0], id: forward[1].id, map: forward[1].sentenceMap, direction: "forward" };
  const back = timing?.translationOf;
  if (back?.id && Array.isArray(back.sentenceMap)) return { lang: back.lang, id: back.id, map: back.sentenceMap, direction: "back" };
  return null;
}

/** Sentence to land on in the other language. A source sentence that became two starts at the first; falls back to the start. */
export function targetSentence(sw, sentence) {
  const mapped = sw.direction === "forward" ? sw.map[sentence]?.[0] : sw.map[sentence];
  return Number.isInteger(mapped) ? mapped : 0;
}

export function firstWordOfSentence(words, sentence) {
  const index = Array.isArray(words) ? words.findIndex((w) => w?.sentence === sentence) : -1;
  return index >= 0 ? index : null;
}

/** Sentence number from the route query (?s=3), or null. */
export function resumeSentence(query) {
  const s = Number(query?.s);
  return query?.s !== undefined && query?.s !== "" && Number.isInteger(s) && s >= 0 ? s : null;
}

export const LANGUAGE_NAMES = { en: "English", es: "Español" };
