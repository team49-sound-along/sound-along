/** Passage summary derived from a timing document. Shared by the file catalog and the DynamoDB seed script. */
export function summarizePassage({ id, timing, mtimeMs, generated }) {
  return {
    id,
    title: timing.title ?? "Untitled passage",
    words: timing.metrics?.words ?? timing.words?.length ?? 0,
    durationMs: timing.duration_ms ?? 0,
    engine: timing.engine ?? "unknown",
    voice: timing.voice ?? "unknown",
    createdAt: new Date(mtimeMs).toISOString(),
    source: generated ? "generated" : "sample",
    vocabCount: Object.keys(timing.vocab ?? {}).length,
    pairId: timing.pairId ?? null,
  };
}
