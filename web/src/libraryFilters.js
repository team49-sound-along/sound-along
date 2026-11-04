// Pure Library filtering. Works on passages already grouped by voices.groupVariants,
// where a paired human recording is recorded on the AI entry as `humanId`.
import { isHuman } from "./voices.js";

export const VOICE_FILTERS = [
  { value: "any", label: "Any voice" },
  { value: "ai", label: "Read-aloud voice" },
  { value: "human", label: "Human recording" },
];

export const LANGUAGE_FILTERS = [
  { value: "all", label: "All languages" },
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
];

export const hasHumanVoice = (p) => Boolean(p) && (isHuman(p) || Boolean(p.humanId));
export const hasAiVoice = (p) => Boolean(p) && !isHuman(p);

const languageOf = (p) => (p?.language === "es" ? "es" : "en");

const matchesVoice = (p, voice) => (voice === "ai" ? hasAiVoice(p) : voice === "human" ? hasHumanVoice(p) : true);
const matchesLanguage = (p, language) => (language === "en" || language === "es" ? languageOf(p) === language : true);
const matchesQuery = (p, q) => !q || String(p?.title ?? "").toLowerCase().includes(q);

/** Returns a new array; unknown voice/language values behave like "no filter". */
export function filterLibrary(passages, { query = "", voice = "any", language = "all" } = {}) {
  if (!Array.isArray(passages)) return [];
  const q = String(query ?? "").trim().toLowerCase();
  return passages.filter((p) => matchesQuery(p, q) && matchesVoice(p, voice) && matchesLanguage(p, language));
}
