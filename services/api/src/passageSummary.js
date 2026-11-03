/** Vocabulary words in a timing document. Its keys are word senses, so "tax" (noun) and "tax" (verb) are two keys but one word. */
const distinctVocabWords = (vocab) =>
  new Set(Object.values(vocab ?? {}).map((entry) => String(entry?.word ?? "").trim().toLowerCase()).filter(Boolean)).size;

/** Passage summary derived from a timing document. `source` is the raw/<id>.json `source` field ("sample" when absent). Shared by the file catalog and the DynamoDB seed script. */
export function summarizePassage({ id, timing, mtimeMs, source }) {
  return {
    id,
    title: timing.title ?? "Untitled passage",
    words: timing.metrics?.words ?? timing.words?.length ?? 0,
    durationMs: timing.duration_ms ?? 0,
    engine: timing.engine ?? "unknown",
    voice: timing.voice ?? "unknown",
    createdAt: new Date(mtimeMs).toISOString(),
    source: source === "generated" ? "generated" : "sample",
    vocabCount: distinctVocabWords(timing.vocab),
    pairId: timing.pairId ?? null,
    language: timing.language === "es" ? "es" : "en",
  };
}

/** The ASR review block of a timing document, or undefined. Stored on the PASSAGE item, never in the public Passage. */
export const reviewOf = (timing) => timing.review ?? undefined;
