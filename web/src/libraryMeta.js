// One muted summary line for a Library row, built only from fields the passage really has.
import { formatCount } from "./format.js";
import { hasHumanVoice } from "./libraryFilters.js";

const count = (n) => (Number.isFinite(n) ? n : null);
const plural = (n, one, many) => `${formatCount(n)} ${n === 1 ? one : many}`;

function voiceText(p) {
  return hasHumanVoice(p) ? "Recording available" : null; // every passage can be read aloud, so only the extra is worth saying
}

export function passageSummary(p) {
  if (!p) return "";
  const words = count(p.words);
  const vocab = count(p.vocabCount);
  return [
    words !== null && words > 0 ? plural(words, "word", "words") : null,
    vocab !== null && vocab > 0 ? plural(vocab, "vocabulary word", "vocabulary words") : null,
    voiceText(p),
  ].filter(Boolean).join(" · ");
}
