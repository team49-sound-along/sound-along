import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { HttpError } from "./http.js";

/** Narration engines a teacher may choose. "kokoro" also covers the Phonon voices (chosen by voice id); "polly" is Amazon Polly. */
export const TTS_ENGINES = Object.freeze(["kokoro", "polly"]);
/** Voice quality for Amazon Polly voices: neural, or the more natural generative one (no word times from Polly; the recognizer supplies them). */
export const POLLY_ENGINES = Object.freeze(["neural", "generative"]);
/** The engine Settings starts with: the deployment's (DEFAULT_TTS_ENGINE, "polly" on AWS), else "kokoro", which runs on a laptop with no AWS account. */
const startingEngine = TTS_ENGINES.includes(process.env.DEFAULT_TTS_ENGINE) ? process.env.DEFAULT_TTS_ENGINE : "kokoro";
export const DEFAULT_SETTINGS = Object.freeze({ voice: "af_heart", voiceEs: "ef_dora", speed: 0.95, mp3Kbps: 48, ttsEngine: startingEngine });
const POLLY_FALLBACK = Object.freeze({ voice: "Ruth", voiceEs: "Lupe" });
const SPEED = { min: 0.7, max: 1.2 };
const KBPS = { min: 24, max: 128 };
const CONFIG_DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "config");
const VOICES_FILE = path.join(CONFIG_DIR, "voices.json");
const POLLY_VOICES_FILE = path.join(CONFIG_DIR, "polly-voices.json");
const POLLY_RATINGS_FILE = path.join(CONFIG_DIR, "polly-voice-ratings.json");

const bad = (message) => {
  throw new HttpError(400, message);
};
const readJson = (file) => JSON.parse(readFileSync(file, "utf8"));

let voicesCache = null;
/** The open-source voices from config/voices.json (read once). Tests can pass another file. */
export function loadVoices(file = VOICES_FILE) {
  if (file === VOICES_FILE && voicesCache) return voicesCache;
  const voices = readJson(file);
  if (file === VOICES_FILE) voicesCache = voices;
  return voices;
}

/** The curated Amazon Polly voices. `recommended` is true only for voices the listening test (polly-voice-ratings.json) approved. */
export function loadPollyVoices({ voices = readJson(POLLY_VOICES_FILE), ratings = readJson(POLLY_RATINGS_FILE) } = {}) {
  const approved = new Set(Array.isArray(ratings?.recommended) ? ratings.recommended : []);
  return voices.map((v) => ({ ...v, recommended: approved.has(v.id) }));
}

let allCache = null;
/** Every voice a deployment can offer: the open-source ones plus Amazon Polly's. The Settings screen shows the ones that fit the chosen engine. */
export function loadAllVoices() {
  allCache ??= [...loadVoices(), ...loadPollyVoices()];
  return allCache;
}

const isPolly = (v) => v.engine === "polly";
const offered = (voices, id, lang, engine) =>
  typeof id === "string" && voices.some((v) => v.id === id && (v.lang ?? "en") === lang && isPolly(v) === (engine === "polly"));

/** The voices each engine starts with: the open-source defaults, or the deployment's POLLY_VOICE / POLLY_VOICE_ES when on the list, else Joanna and Lupe. */
export function defaultVoices(engine, voices = loadAllVoices()) {
  if (engine !== "polly") return { voice: DEFAULT_SETTINGS.voice, voiceEs: DEFAULT_SETTINGS.voiceEs };
  const pick = (envName, lang, fallback) => (offered(voices, process.env[envName], lang, "polly") ? process.env[envName] : fallback);
  return { voice: pick("POLLY_VOICE", "en", POLLY_FALLBACK.voice), voiceEs: pick("POLLY_VOICE_ES", "es", POLLY_FALLBACK.voiceEs) };
}

const engineLabel = (engine) => (engine === "polly" ? "Amazon Polly" : "the built-in voices");

/** Validate a (possibly partial) settings body. Returns only the fields that were sent. `currentEngine` is the engine already saved,
 *  used to check a voice sent without an engine. */
export function parseSettingsPatch(body, voices, currentEngine = DEFAULT_SETTINGS.ttsEngine) {
  if (body === null || typeof body !== "object" || Array.isArray(body)) bad("Send a JSON object.");
  const patch = {};
  if ("ttsEngine" in body) {
    if (!TTS_ENGINES.includes(body.ttsEngine)) bad(`Narration engine must be one of: ${TTS_ENGINES.join(", ")}.`);
    patch.ttsEngine = body.ttsEngine;
  }
  const engine = patch.ttsEngine ?? (TTS_ENGINES.includes(currentEngine) ? currentEngine : DEFAULT_SETTINGS.ttsEngine);
  const voiceField = (key, lang, name) => {
    if (!(key in body)) return;
    if (!offered(voices, body[key], lang, engine)) {
      bad(
        voices.some((v) => v.id === body[key] && (v.lang ?? "en") === lang)
          ? `That ${name} voice is not available with ${engineLabel(engine)}. Choose a ${name} voice from the list.`
          : `Choose a ${name} voice from the list.`,
      );
    }
    patch[key] = body[key];
  };
  voiceField("voice", "en", "English");
  voiceField("voiceEs", "es", "Spanish");
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
  if ("pollyEngine" in body) {
    if (!POLLY_ENGINES.includes(body.pollyEngine)) bad(`Voice quality must be one of: ${POLLY_ENGINES.join(", ")}.`);
    patch.pollyEngine = body.pollyEngine;
  }
  if (Object.keys(patch).length === 0) bad("Send at least one of voice, voiceEs, speed, mp3Kbps, ttsEngine or pollyEngine.");
  return patch;
}

/** Stored settings (any subset) over the defaults, as a new object. Unknown stored keys are dropped, and a stored voice that is not offered for the
 *  engine in force (for example an open-source voice saved before the deployment moved to Polly) falls back to that engine's default voice. */
export function effectiveSettings(stored, voices = loadAllVoices()) {
  const ttsEngine = TTS_ENGINES.includes(stored?.ttsEngine) ? stored.ttsEngine : DEFAULT_SETTINGS.ttsEngine;
  const fallback = defaultVoices(ttsEngine, voices);
  return {
    voice: offered(voices, stored?.voice, "en", ttsEngine) ? stored.voice : fallback.voice,
    voiceEs: offered(voices, stored?.voiceEs, "es", ttsEngine) ? stored.voiceEs : fallback.voiceEs,
    speed: stored?.speed ?? DEFAULT_SETTINGS.speed,
    mp3Kbps: stored?.mp3Kbps ?? DEFAULT_SETTINGS.mp3Kbps,
    ttsEngine,
    ...(POLLY_ENGINES.includes(stored?.pollyEngine) ? { pollyEngine: stored.pollyEngine } : {}),
  };
}

/** Current settings with the patch applied; voices are re-checked against the resulting engine. */
export const mergeSettings = (current, patch, voices = loadAllVoices()) => effectiveSettings({ ...effectiveSettings(current, voices), ...patch }, voices);

const deploymentPollyEngine = () => (POLLY_ENGINES.includes(process.env.POLLY_ENGINE) ? process.env.POLLY_ENGINE : "neural");

/** What GET /settings returns: the settings, every voice, each engine's default voices and the voice quality in force. */
export const settingsView = (stored, voices) => {
  const settings = effectiveSettings(stored, voices);
  return {
    ...settings,
    pollyEngine: settings.pollyEngine ?? deploymentPollyEngine(),
    voiceDefaults: { kokoro: defaultVoices("kokoro", voices), polly: defaultVoices("polly", voices) },
    voices,
  };
};
