import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { HttpError } from "./http.js";

export const DEFAULT_SETTINGS = Object.freeze({ voice: "af_heart", voiceEs: "ef_dora", speed: 0.95, mp3Kbps: 48, ttsEngine: "kokoro" });
/** Narration engines a teacher may choose. "kokoro" also covers the Phonon voices (chosen by voice id); "polly" is Amazon Polly. */
export const TTS_ENGINES = Object.freeze(["kokoro", "polly"]);
const SPEED = { min: 0.7, max: 1.2 };
const KBPS = { min: 24, max: 128 };
const VOICES_FILE = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "config", "voices.json");

const bad = (message) => {
  throw new HttpError(400, message);
};

let voicesCache = null;
/** Voice list from config/voices.json (read once). Tests and other deployments can pass `config.voices` instead. */
export function loadVoices(file = VOICES_FILE) {
  if (file === VOICES_FILE && voicesCache) return voicesCache;
  const voices = JSON.parse(readFileSync(file, "utf8"));
  if (file === VOICES_FILE) voicesCache = voices;
  return voices;
}

/** Validate a (possibly partial) settings body. Returns only the fields that were sent. */
export function parseSettingsPatch(body, voices) {
  if (body === null || typeof body !== "object" || Array.isArray(body)) bad("Send a JSON object.");
  const patch = {};
  if ("voice" in body) {
    if (typeof body.voice !== "string" || !voices.some((v) => v.id === body.voice && (v.lang ?? "en") === "en")) {
      bad("Choose an English voice from the list.");
    }
    patch.voice = body.voice;
  }
  if ("voiceEs" in body) {
    if (typeof body.voiceEs !== "string" || !voices.some((v) => v.id === body.voiceEs && v.lang === "es")) {
      bad("Choose a Spanish voice from the list.");
    }
    patch.voiceEs = body.voiceEs;
  }
  if ("speed" in body) {
    const { speed } = body;
    if (typeof speed !== "number" || !Number.isFinite(speed) || speed < SPEED.min || speed > SPEED.max) {
      bad(`Speed must be a number from ${SPEED.min} to ${SPEED.max}.`);
    }
    patch.speed = speed;
  }
  if ("mp3Kbps" in body) {
    const { mp3Kbps } = body;
    if (!Number.isInteger(mp3Kbps) || mp3Kbps < KBPS.min || mp3Kbps > KBPS.max) {
      bad(`MP3 quality must be a whole number from ${KBPS.min} to ${KBPS.max} kbps.`);
    }
    patch.mp3Kbps = mp3Kbps;
  }
  if ("ttsEngine" in body) {
    if (!TTS_ENGINES.includes(body.ttsEngine)) bad(`Narration engine must be one of: ${TTS_ENGINES.join(", ")}.`);
    patch.ttsEngine = body.ttsEngine;
  }
  if (Object.keys(patch).length === 0) bad("Send at least one of voice, voiceEs, speed, mp3Kbps or ttsEngine.");
  return patch;
}

/** Stored settings (any subset) over the defaults, as a new object. Unknown stored keys are dropped, and a stored voice that is no longer offered falls back to the default. */
export function effectiveSettings(stored, voices = loadVoices()) {
  const offered = (id, lang) => voices.some((v) => v.id === id && (v.lang ?? "en") === lang);
  return {
    voice: offered(stored?.voice, "en") ? stored.voice : DEFAULT_SETTINGS.voice,
    voiceEs: offered(stored?.voiceEs, "es") ? stored.voiceEs : DEFAULT_SETTINGS.voiceEs,
    speed: stored?.speed ?? DEFAULT_SETTINGS.speed,
    mp3Kbps: stored?.mp3Kbps ?? DEFAULT_SETTINGS.mp3Kbps,
    ttsEngine: TTS_ENGINES.includes(stored?.ttsEngine) ? stored.ttsEngine : DEFAULT_SETTINGS.ttsEngine,
  };
}

export const mergeSettings = (current, patch) => ({ ...effectiveSettings(current), ...patch });
