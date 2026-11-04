// Thin client for the /api envelope: { success, data, error, meta }.
import { sha256Hex } from "./hash.js";

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const NETWORK = "Cannot reach the Sound Along server. Check your connection and try again.";

async function request(method, path, body, signal) {
  let res;
  try {
    const payload = body === undefined ? undefined : JSON.stringify(body);
    res = await fetch(path, {
      method,
      signal,
      headers:
        payload === undefined
          ? undefined
          : { "Content-Type": "application/json", "x-amz-content-sha256": await sha256Hex(payload) },
      body: payload,
    });
  } catch (e) {
    if (e?.name === "AbortError") throw e;
    throw new ApiError(NETWORK, 0);
  }
  let envelope = null;
  try {
    envelope = await res.json();
  } catch {
    /* non-JSON body handled below */
  }
  if (!res.ok || !envelope || envelope.success !== true) {
    throw new ApiError(envelope?.error || "Something went wrong. Please try again in a moment.", res.status);
  }
  return envelope.data;
}

export const api = {
  health: () => request("GET", "/api/health"),
  passages: () => request("GET", "/api/passages"),
  /** Passages still being made (parts or the translation not finished). A teacher sees them as "Being created"; they are never offered for reading. */
  pendingPassages: () => request("GET", "/api/passages?pending=1"),
  classes: () => request("GET", "/api/classes"),
  assignments: () => request("GET", "/api/assignments"),
  createAssignment: (body) => request("POST", "/api/assignments", body),
  setSoundAlong: (id, soundAlong) => request("PATCH", `/api/assignments/${encodeURIComponent(id)}`, { soundAlong }),
  deleteAssignment: (id) => request("DELETE", `/api/assignments/${encodeURIComponent(id)}`),
  generate: (body) => request("POST", "/api/generate", body),
  settings: () => request("GET", "/api/settings"),
  saveSettings: (body) => request("PUT", "/api/settings", body),
  pronunciations: () => request("GET", "/api/pronunciations"),
  savePronunciation: (word, respelling) => request("PUT", `/api/pronunciations/${encodeURIComponent(word)}`, { respelling }),
  deletePronunciation: (word) => request("DELETE", `/api/pronunciations/${encodeURIComponent(word)}`),
  createRecording: (body) => request("POST", "/api/recordings", body),
  review: () => request("GET", "/api/review"),
  dismissReview: (word) => request("POST", "/api/review/dismiss", { word }),
  regenerate: (passageId) => request("POST", `/api/passages/${encodeURIComponent(passageId)}/regenerate`, {}),
  job: (id) => request("GET", `/api/jobs/${encodeURIComponent(id)}`),
  ratingTrial: () => request("GET", "/api/ratings/trial"),
  submitRating: (body) => request("POST", "/api/ratings", body),
  insights: () => request("GET", "/api/insights"),
  /** Teacher: passages that have unreviewed question drafts, one draft, and publishing the approved questions (students only ever see what is published). */
  questionDrafts: () => request("GET", "/api/questions/drafts"),
  questionDraft: (id) => request("GET", `/api/questions/drafts/${encodeURIComponent(id)}`),
  publishQuestions: (id, body) => request("POST", `/api/questions/drafts/${encodeURIComponent(id)}/publish`, body),
  /** Fire and forget: analytics must never break reading. */
  event: (body) => {
    request("POST", "/api/events", body).catch(() => {});
  },
};

/**
 * The passage list as a document: ReadWorks' guide says the frontend reads JSON documents and does no processing, so the
 * list comes from data/index.json (an S3 object on AWS). If the document is missing or malformed, fall back to the API.
 */
export async function passageIndex(fetchFn = globalThis.fetch) {
  try {
    const res = await fetchFn("/data/index.json", { cache: "no-cache" });
    if (res.ok) {
      const list = await res.json();
      if (Array.isArray(list)) return list;
    }
  } catch {
    /* fall through to the API */
  }
  return api.passages();
}

/**
 * Word and place cards: a static JSON document next to the timing file (docs/CARDS.md), like the rest of the content.
 * Cards are optional, so a missing, offline or malformed document gives null and the reader uses the passage vocabulary.
 */
export async function fetchCards(id, fetchFn = globalThis.fetch) {
  try {
    const res = await fetchFn(`/data/${encodeURIComponent(id)}.cards.json`);
    if (!res.ok) return null;
    const doc = await res.json();
    const isMap = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
    return isMap(doc) ? { words: isMap(doc.words) ? doc.words : {}, places: isMap(doc.places) ? doc.places : {}, figures: Array.isArray(doc.figures) ? doc.figures : [] } : null;
  } catch {
    return null;
  }
}

/**
 * The approved questions document next to the timing file (docs/QUESTIONS.md). Optional: a missing, offline or malformed document gives null.
 * It is revalidated on every load, so a teacher's newest publish is what a student sees.
 */
export async function fetchQuestions(id, fetchFn = globalThis.fetch) {
  try {
    const res = await fetchFn(`/data/${encodeURIComponent(id)}.questions.json`, { cache: "no-cache" });
    if (!res.ok) return null;
    const doc = await res.json();
    return doc !== null && typeof doc === "object" && !Array.isArray(doc) ? doc : null;
  } catch {
    return null;
  }
}

/** Static timing file (not enveloped). */
export async function fetchTiming(id) {
  let res;
  try {
    res = await fetch(`/data/${encodeURIComponent(id)}.timing.json`);
  } catch {
    throw new ApiError(NETWORK, 0);
  }
  if (res.status === 404) throw new ApiError("This passage could not be found.", 404);
  if (!res.ok) throw new ApiError("Could not load this passage. Please try again.", res.status);
  try {
    return await res.json();
  } catch {
    throw new ApiError("This passage's timing data is unreadable.", res.status);
  }
}

export const audioUrl = (id) => `/data/${encodeURIComponent(id)}.mp3`;
