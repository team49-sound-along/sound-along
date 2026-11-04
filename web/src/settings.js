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
  { id: "polly", label: "Amazon Polly", hint: "AWS text-to-speech, billed per character. Uses Polly's own voices (Joanna for English, Lupe for Spanish); the voice choices below do not apply." },
];
export const DEFAULT_TTS_ENGINE = "polly"; // what a deployment starts with; the server's own default (a laptop without AWS starts with kokoro) always arrives with the settings

/** Body for PUT /api/settings from form state. */
export const settingsPayload = ({ voice, voiceEs, speed, mp3Kbps, ttsEngine }) => ({
  voice,
  ...(voiceEs ? { voiceEs } : {}),
  speed: snapSpeed(speed),
  mp3Kbps: Number(mp3Kbps),
  ...(ttsEngine ? { ttsEngine } : {}),
});

export const isDirty = (saved, form) =>
  !saved || saved.voice !== form.voice || (saved.voiceEs ?? "") !== (form.voiceEs ?? "") || snapSpeed(saved.speed) !== snapSpeed(form.speed) || saved.mp3Kbps !== Number(form.mp3Kbps) ||
  (saved.ttsEngine ?? DEFAULT_TTS_ENGINE) !== (form.ttsEngine || DEFAULT_TTS_ENGINE);
