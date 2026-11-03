// Blind A/B listening test logic (docs/API.md v3). Pure helpers; the view only wires them up.
export const RATING_VALUES = [1, 2, 3, 4, 5];
export const RATING_ENDS = { 1: "1 sounds robotic", 5: "5 sounds like a person" };
export const PREFERENCES = [
  { value: "a", label: "Reading A" },
  { value: "b", label: "Reading B" },
  { value: "tie", label: "No difference" },
];
const RATER_KEY = "soundalong.raterId";
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function makeUuid() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = new Uint8Array(16);
  if (typeof crypto !== "undefined" && crypto.getRandomValues) crypto.getRandomValues(b);
  else for (let i = 0; i < 16; i++) b[i] = Math.floor(Math.random() * 256);
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

let sessionId = null;
/** Stable anonymous rater id: localStorage when available, otherwise one per page session. */
export function getRaterId(storage, make = makeUuid) {
  try {
    const existing = storage?.getItem(RATER_KEY);
    if (existing && UUID_RE.test(existing)) return existing;
    const fresh = make();
    storage.setItem(RATER_KEY, fresh);
    return fresh;
  } catch {
    sessionId ??= make();
    return sessionId;
  }
}
export const resetSessionRaterId = () => (sessionId = null);

export const emptyAnswer = () => ({ ratingA: null, ratingB: null, preferred: null });

export const isComplete = (a) =>
  RATING_VALUES.includes(a?.ratingA) && RATING_VALUES.includes(a?.ratingB) && PREFERENCES.some((p) => p.value === a?.preferred);

/** Body for POST /api/ratings. Uses only the tokens the server sent. */
export const ratingPayload = (trial, answer, raterId) => ({
  trialId: trial.trialId,
  aToken: trial.a.token,
  bToken: trial.b.token,
  preferred: answer.preferred,
  ratingA: answer.ratingA,
  ratingB: answer.ratingB,
  raterId,
});

/** A trial must carry two playable urls, otherwise it is treated as unusable. */
export const isUsableTrial = (t) => Boolean(t?.trialId && t.a?.token && t.a?.url && t.b?.token && t.b?.url);

export function ratingErrorMessage(status, fallback) {
  if (status === 429) return "You are going a little fast. Wait a minute, then submit again.";
  if (status === 503) return "Rating is turned off on this server right now. Please try again later.";
  if (status === 400) return fallback || "That rating could not be saved. Load the next clip and try again.";
  return fallback || "Something went wrong saving your rating. Please try again.";
}

export function trialLoadMessage(status, fallback) {
  if (status === 429) return "Too many requests right now. Wait a minute, then try again.";
  if (status === 503) return "The listening test is turned off on this server right now.";
  return fallback || "We could not load a listening clip. Please try again.";
}

export const completedLabel = (n) => (n === 1 ? "1 trial completed this session" : `${n} trials completed this session`);
