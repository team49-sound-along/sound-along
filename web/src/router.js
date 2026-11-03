// Minimal hash router (pure parse + reactive current route).
import { ref, readonly } from "vue";

export function parseHash(hash) {
  const raw = String(hash || "").replace(/^#\/?/, "");
  const [path, queryString = ""] = raw.split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  const query = Object.fromEntries(new URLSearchParams(queryString));
  const [name = "library", id] = parts;
  if (name === "read" && id) return { name: "read", params: { id }, query };
  if (["library", "assignments", "generate", "insights"].includes(name)) return { name, params: {}, query };
  return { name: "library", params: {}, query: {} };
}

const current = ref(parseHash(typeof location === "undefined" ? "" : location.hash));
if (typeof window !== "undefined") {
  window.addEventListener("hashchange", () => (current.value = parseHash(location.hash)));
}
export const route = readonly(current);
