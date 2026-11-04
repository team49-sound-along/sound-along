// How the read-aloud follower reacts to a missed word, remembered on this device only.
//   keepGoing  (default)  the learner keeps reading; a calm reminder offers to go back
//   stop                  listening pauses and the learner is guided back right away
import { safeStorage } from "./practice.js";

export const MODE_KEY = "soundalong.readAloudMode.v1";
export const MODES = ["keepGoing", "stop"];

export function loadMode(storage = safeStorage()) {
  try {
    const saved = storage?.getItem(MODE_KEY);
    return MODES.includes(saved) ? saved : "keepGoing";
  } catch {
    return "keepGoing";
  }
}

export function saveMode(mode, storage = safeStorage()) {
  if (!MODES.includes(mode)) return false;
  try {
    storage?.setItem(MODE_KEY, mode);
    return Boolean(storage);
  } catch {
    return false;
  }
}
