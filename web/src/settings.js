// Settings helpers (limits mirror docs/API.md v2).
export const SPEED_MIN = 0.7;
export const SPEED_MAX = 1.2;
export const SPEED_STEP = 0.05;
export const KBPS_OPTIONS = [24, 32, 48, 64, 96, 128];

/** Approximate MP3 size per minute of narration, in MB (kbps * 60 / 8 / 1000). */
export const mbPerMinute = (kbps) => Math.round(((kbps * 60) / 8 / 1000) * 100) / 100;

export const formatSpeed = (v) => `${Number(v).toFixed(2)}x`;

/** Snap a slider value to the step grid, avoiding float noise like 0.9500000001. */
export const snapSpeed = (v) => Math.min(SPEED_MAX, Math.max(SPEED_MIN, Math.round(Number(v) / SPEED_STEP) * SPEED_STEP)).toFixed(2) * 1;

/** Narration engines (mirror services/api/src/settings.js TTS_ENGINES). */
export const TTS_ENGINE_OPTIONS = [
  { id: "kokoro", label: "Built-in voices", hint: "Runs inside Sound Along. Uses the English and Spanish voices chosen below." },
  { id: "polly", label: "Amazon Polly", hint: "AWS text-to-speech, billed per character. Choose its English and Spanish voices below." },
];

/** Voice quality for Amazon Polly voices. Generative voices come without word times, so highlighting relies on speech recognition for them. */
export const POLLY_QUALITY_OPTIONS = [
  { id: "neural", label: "Natural (neural)", hint: "Word highlighting uses timing from the voice service." },
  { id: "generative", label: "Most natural (generative)", hint: "Word highlighting is timed by speech recognition, so a word can occasionally be out of step. A voice that does not offer this quality uses the one it has." },
];
export const DEFAULT_POLLY_QUALITY = "neural";

const isPollyVoice = (v) => v.engine === "polly";

/** Voices of one language that belong to the chosen narration engine: Polly's own for "polly", the built-in ones otherwise. */
export const voicesForEngine = (voices, engine, lang) =>
  (Array.isArray(voices) ? voices : []).filter((v) => (v.lang ?? "en") === lang && isPollyVoice(v) === (engine === "polly"));

/** Menu groups: recommended voices first, the rest under "More voices". With nothing recommended yet there is one plain list (no quality claim). */
export function voiceGroups(list, engine) {
  const recommended = list.filter((v) => (engine === "polly" ? v.recommended === true : v.recommended !== false));
  const more = list.filter((v) => !recommended.includes(v));
  if (recommended.length === 0) return more.length ? [{ label: "Voices", voices: more }] : [];
  const first = { label: engine === "polly" ? "Recommended voices" : "Recommended (passed our listening test)", voices: recommended };
  return more.length ? [first, { label: engine === "polly" ? "More voices" : "More voices to try (less natural)", voices: more }] : [first];
}

/** The form with another narration engine chosen: a voice the new engine does not offer becomes that engine's default voice (from the server, else the first listed). */
export function formForEngine(form, engine, voices, defaults) {
  const pick = (current, lang, key) => {
    const list = voicesForEngine(voices, engine, lang);
    return list.some((v) => v.id === current) ? current : defaults?.[engine]?.[key] ?? list[0]?.id ?? "";
  };
  return { ...form, ttsEngine: engine, voice: pick(form.voice, "en", "voice"), voiceEs: pick(form.voiceEs, "es", "voiceEs") };
}

/** File name (without .mp3) of a voice's "Hear it" sample in web/public/voice-samples. */
export const sampleFile = (voice, engine) => (!voice ? "" : engine === "polly" ? `polly-${voice}` : voice);
export const DEFAULT_TTS_ENGINE = "polly"; // what a deployment starts with; the server's own default (a laptop without AWS starts with kokoro) always arrives with the settings

/** Body for PUT /api/settings from form state. */
export const settingsPayload = ({ voice, voiceEs, speed, mp3Kbps, ttsEngine, pollyEngine }) => ({
  voice,
  ...(voiceEs ? { voiceEs } : {}),
  speed: snapSpeed(speed),
  mp3Kbps: Number(mp3Kbps),
  ...(ttsEngine ? { ttsEngine } : {}),
  ...(pollyEngine ? { pollyEngine } : {}),
});

export const isDirty = (saved, form) =>
  !saved || saved.voice !== form.voice || (saved.voiceEs ?? "") !== (form.voiceEs ?? "") || snapSpeed(saved.speed) !== snapSpeed(form.speed) || saved.mp3Kbps !== Number(form.mp3Kbps) ||
  (saved.ttsEngine ?? DEFAULT_TTS_ENGINE) !== (form.ttsEngine || DEFAULT_TTS_ENGINE) ||
  (saved.pollyEngine ?? DEFAULT_POLLY_QUALITY) !== (form.pollyEngine || DEFAULT_POLLY_QUALITY);
