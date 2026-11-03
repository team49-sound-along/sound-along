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
    throw new ApiError(envelope?.error || `The server returned an unexpected response (HTTP ${res.status}).`, res.status);
  }
  return envelope.data;
}

export const api = {
  health: () => request("GET", "/api/health"),
  passages: () => request("GET", "/api/passages"),
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
  insights: () => request("GET", "/api/insights"),
  /** Fire and forget: analytics must never break reading. */
  event: (body) => {
    request("POST", "/api/events", body).catch(() => {});
  },
};

/** Static timing file (not enveloped). */
export async function fetchTiming(id) {
  let res;
  try {
    res = await fetch(`/data/${encodeURIComponent(id)}.timing.json`);
  } catch {
    throw new ApiError(NETWORK, 0);
  }
  if (res.status === 404) throw new ApiError("This passage could not be found.", 404);
  if (!res.ok) throw new ApiError(`Could not load this passage (HTTP ${res.status}).`, res.status);
  try {
    return await res.json();
  } catch {
    throw new ApiError("This passage's timing data is unreadable.", res.status);
  }
}

export const audioUrl = (id) => `/data/${encodeURIComponent(id)}.mp3`;
