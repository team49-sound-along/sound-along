import { HttpError } from "./http.js";
import { UUID } from "./recordings/rules.js";

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const EVENT_TYPES = new Set(["play", "word_tap", "complete"]);

export const LIMITS = { titleMax: 120, textMin: 20, textMax: 12000 };

const bad = (message) => {
  throw new HttpError(400, message);
};
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

export function parseAssignmentInput(body, { passageIds, classIds }) {
  if (!isObject(body)) bad("Send a JSON object.");
  const { passageId, classId, soundAlong, dueDate } = body;
  if (!passageIds.has(passageId)) bad("Choose a passage from the library.");
  if (!classIds.has(classId)) bad("Choose one of your classes.");
  if (typeof soundAlong !== "boolean") bad("Say whether Sound Along is on or off.");
  if (dueDate != null && !(typeof dueDate === "string" && DATE.test(dueDate) && !Number.isNaN(Date.parse(dueDate)))) {
    bad("Due date must look like 2026-11-20.");
  }
  return { passageId, classId, soundAlong, dueDate: dueDate ?? null };
}

export function parseToggle(body) {
  if (!isObject(body) || typeof body.soundAlong !== "boolean") bad("Say whether Sound Along is on or off.");
  return { soundAlong: body.soundAlong };
}

export function parseGenerateInput(body) {
  if (!isObject(body)) bad("Send a JSON object.");
  const title = typeof body.title === "string" ? body.title.trim() : "";
  const text = typeof body.text === "string" ? body.text.replace(/\r\n/g, "\n").trim() : "";
  if (title.length < 1 || title.length > LIMITS.titleMax) bad(`Title must be 1 to ${LIMITS.titleMax} characters.`);
  if (text.length < LIMITS.textMin) bad(`Add at least ${LIMITS.textMin} characters of text.`);
  if (text.length > LIMITS.textMax) bad(`Text can be at most ${LIMITS.textMax.toLocaleString("en-US")} characters.`);
  let recordingId = null;
  if (body.recordingId != null) {
    if (typeof body.recordingId !== "string" || !UUID.test(body.recordingId)) bad("That recording id is not valid. Upload the recording again.");
    recordingId = body.recordingId;
  }
  return { title, text, recordingId };
}

export function parseEvent(body, passageIds) {
  if (!isObject(body)) bad("Send a JSON object.");
  if (!EVENT_TYPES.has(body.type)) bad("Unknown event type.");
  if (!passageIds.has(body.passageId)) bad("Unknown passage.");
  return { type: body.type, passageId: body.passageId };
}

const escapeHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** Plain text -> the same <p> structure the parser expects from ReadWorks content. */
export function textToHtml(text) {
  return text
    .split(/\n{1,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean)
    .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
    .join("\n");
}
