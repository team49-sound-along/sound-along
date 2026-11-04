// Minimal hash router (pure parse + reactive current route).
import { ref, readonly } from "vue";

const PAGES = ["library", "assignments", "generate", "insights", "settings", "pronunciations", "review", "listening", "words", "questions"];
/** Teacher "Voice" section: four related screens shown under one nav item with shared tabs. */
export const VOICE_SECTION = ["settings", "pronunciations", "review", "listening"];
/** Screens only a teacher may open (the API has no real auth; this is the demo role guard). */
export const TEACHER_ONLY = ["generate", "insights", "settings", "pronunciations", "review", "questions"];
export const isTeacherOnly = (name) => TEACHER_ONLY.includes(name);

export function parseHash(hash) {
  const raw = String(hash || "").replace(/^#\/?/, "");
  const [path, queryString = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const query = Object.fromEntries(new URLSearchParams(queryString));
  const [name = "library", id] = parts;
  if (["read", "practice", "quiz", "questions"].includes(name) && id) return { name, params: { id }, query };
  if (PAGES.includes(name)) return { name, params: {}, query };
  return { name: "library", params: {}, query: {} };
}

const current = ref(parseHash(typeof location === "undefined" ? "" : location.hash));
if (typeof window !== "undefined") {
  window.addEventListener("hashchange", () => (current.value = parseHash(location.hash)));
}
export const route = readonly(current);
