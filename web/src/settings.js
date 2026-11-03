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

/** Body for PUT /api/settings from form state. */
export const settingsPayload = ({ voice, speed, mp3Kbps }) => ({ voice, speed: snapSpeed(speed), mp3Kbps: Number(mp3Kbps) });

export const isDirty = (saved, form) =>
  !saved || saved.voice !== form.voice || snapSpeed(saved.speed) !== snapSpeed(form.speed) || saved.mp3Kbps !== Number(form.mp3Kbps);
