// Teacher switches for reading aloud, kept per class with a school-wide default (both default to ON):
//   mic    "Read aloud with the microphone": when off, students in the class do not get the button
//   share  "Share anonymous word counts with the teacher": when off, nothing is sent and the server drops anything that arrives
// Stored like the other class-level choices: one record per class plus one for the default.
import { HttpError } from "../http.js";

export const DEFAULT_KEY = "DEFAULT";
//   readers "Show progress by reader (anonymous codes)": default OFF. Only when it is on does a device add its random reader code, and only
//           then does the server keep or show codes for the class. It needs sharing: without sharing nothing is kept at all.
export const HARD_DEFAULTS = Object.freeze({ mic: true, share: true, readers: false });
const FIELDS = ["mic", "share", "readers"];
const bad = (message) => {
  throw new HttpError(400, message);
};

/** The two switches in force for a class (or for no class), as a new object. */
export function effectiveClassSettings(stored, classId = null) {
  const pick = (field) => stored?.[classId]?.[field] ?? stored?.[DEFAULT_KEY]?.[field] ?? HARD_DEFAULTS[field];
  const share = pick("share");
  return { mic: pick("mic"), share, readers: share && pick("readers") };
}

/** { classId?: string|null, mic?: boolean, share?: boolean } -> { key, patch }. No classId changes the default for every class. */
export function parseClassSettingsPatch(body, classIds) {
  if (body === null || typeof body !== "object" || Array.isArray(body)) bad("Send a JSON object.");
  if (Object.keys(body).some((k) => k !== "classId" && !FIELDS.includes(k))) bad("Unknown field.");
  const { classId } = body;
  if (classId != null && !(typeof classId === "string" && classIds.has(classId))) bad("Choose one of your classes.");
  const patch = {};
  for (const field of FIELDS) {
    if (field in body) {
      if (typeof body[field] !== "boolean") bad("Say whether each switch is on or off.");
      patch[field] = body[field];
    }
  }
  if (Object.keys(patch).length === 0) bad("Send at least one of mic, share or readers.");
  return { key: classId ?? DEFAULT_KEY, patch };
}

/** What the screens read: the default and each class with the value in force. */
export function classSettingsView(stored, classes) {
  return {
    defaults: effectiveClassSettings(stored, null),
    classes: classes.map((c) => ({ id: c.id, name: c.name, ...effectiveClassSettings(stored, c.id) })),
  };
}
