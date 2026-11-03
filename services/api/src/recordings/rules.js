import { HttpError } from "../http.js";

export const MAX_RECORDING_BYTES = 25 * 1024 * 1024;
export const RECORDING_TYPES = Object.freeze(["audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/x-m4a", "audio/webm"]);
export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const FILENAME_MAX = 120;

const bad = (message) => {
  throw new HttpError(400, message);
};

export function parseRecordingInput(body) {
  if (body === null || typeof body !== "object" || Array.isArray(body)) bad("Send a JSON object.");
  const filename = typeof body.filename === "string" ? body.filename.trim() : "";
  if (filename.length < 1 || filename.length > FILENAME_MAX) bad(`The file name must be 1 to ${FILENAME_MAX} characters.`);
  if (!RECORDING_TYPES.includes(body.contentType)) bad("Upload an MP3, WAV, M4A, MP4 or WebM audio file.");
  const { size } = body;
  if (!Number.isInteger(size) || size < 1) bad("The recording is empty.");
  if (size > MAX_RECORDING_BYTES) bad("The recording is larger than 25 MB. Upload a shorter or smaller file.");
  return { filename, contentType: body.contentType, size };
}

export const recordingKey = (recordingId) => `raw/${recordingId}.audio`;
