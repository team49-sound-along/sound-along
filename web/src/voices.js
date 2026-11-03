// Voice variants: a passage can have an AI-voice version and a human-narrated version of the same text.
// The API exposes them as two passages linked by `pairId`; the UI shows them as one card with a voice toggle.

export const isHuman = (passage) => passage?.engine === "human";

export const voiceLabel = (engine) => (engine === "human" ? "Human narrator" : "AI voice");

/** One entry per text. Hides a human variant when its AI pair is present and records it as `humanId`. */
export function groupVariants(passages) {
  const ids = new Set(passages.map((p) => p.id));
  const humanByAi = new Map(passages.filter((p) => isHuman(p) && p.pairId && ids.has(p.pairId)).map((p) => [p.pairId, p.id]));
  return passages
    .filter((p) => !(isHuman(p) && p.pairId && ids.has(p.pairId)))
    .map((p) => (humanByAi.has(p.id) ? { ...p, humanId: humanByAi.get(p.id) } : p));
}

/** Which passage id "Read" opens: the human narration when one exists (ReadWorks' best audio), else the passage. */
export const readTarget = (passage) => passage.humanId ?? passage.id;

/** Position to resume at after switching voice: a valid word index from the route query, else null. */
export function resumeIndex(query, wordCount) {
  const at = Number(query?.at);
  return Number.isInteger(at) && at >= 0 && at < wordCount ? at : null;
}
