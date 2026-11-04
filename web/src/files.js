// Client-side checks for files the teacher adds. Limits mirror docs/API.md (v2). The server checks again.
export const TEXT_FILE_MAX_BYTES = 100 * 1024;
export const RECORDING_MAX_BYTES = 26_214_400;
export const FILENAME_MAX = 120;

const RECORDING_TYPES = { mp3: "audio/mpeg", wav: "audio/wav", m4a: "audio/x-m4a", mp4: "audio/mp4", webm: "audio/webm" };
const ALLOWED_TYPES = new Set(["audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/x-m4a", "audio/webm"]);

const extensionOf = (name) => (String(name).match(/\.([^.]+)$/)?.[1] ?? "").toLowerCase();

/** Filename without its extension, trimmed and capped at `max` characters. */
export function titleFromFilename(name, max = 120) {
  return String(name).replace(/\.[^.]*$/, "").trim().slice(0, max);
}

export const formatBytes = (n) => (n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

const FILE_LIMITS = { txt: TEXT_FILE_MAX_BYTES, md: TEXT_FILE_MAX_BYTES, docx: 15 * 1024 * 1024, pdf: 25 * 1024 * 1024 };
const LIMIT_TEXT = { txt: "100 KB", md: "100 KB", docx: "15 MB", pdf: "25 MB" };

/** {ok:true} or {ok:false, error}. Accepts .txt and .md up to 100 KB, .docx up to 15 MB and .pdf up to 25 MB. */
export function validateTextFile(file) {
  if (!file) return { ok: false, error: "Choose a file." };
  const kind = extensionOf(file.name);
  if (!(kind in FILE_LIMITS)) return { ok: false, error: "Choose a .txt, .md, .docx or .pdf file, or paste the text into the box." };
  if (file.size > FILE_LIMITS[kind]) return { ok: false, error: `That file is ${formatBytes(file.size)}. Files of this kind can be up to ${LIMIT_TEXT[kind]}.` };
  return { ok: true };
}

/** {ok:true, contentType} or {ok:false, error}. MP3, WAV, MP4/M4A or WebM up to 25 MB. */
export function validateRecording(file) {
  if (!file) return { ok: false, error: "Choose a recording." };
  const contentType = ALLOWED_TYPES.has(file.type) ? file.type : RECORDING_TYPES[extensionOf(file.name)];
  if (!contentType) return { ok: false, error: "Recordings must be MP3, WAV, M4A/MP4 or WebM audio." };
  if (file.size <= 0) return { ok: false, error: "That recording is empty." };
  if (file.size > RECORDING_MAX_BYTES) return { ok: false, error: `That recording is ${formatBytes(file.size)}. The limit is 25 MB.` };
  if (file.name.length > FILENAME_MAX) return { ok: false, error: `Rename the file so its name is ${FILENAME_MAX} characters or fewer.` };
  return { ok: true, contentType };
}
