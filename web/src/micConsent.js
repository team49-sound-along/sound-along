// Consent for "Read aloud with the microphone". The browser's speech recognition sends the voice to the browser maker's speech service
// (Chrome and Edge to their own online service, Safari to Apple), so nothing is listened to until the reader has agreed on this device.
// The choice is kept in this browser only, and can be taken back. See practice.js for the wider privacy statement.
import { safeStorage } from "./practice.js";

export const CONSENT_KEY = "soundalong.micConsent.v1";

export const hasMicConsent = (storage = safeStorage()) => {
  try {
    return storage?.getItem(CONSENT_KEY) === "yes";
  } catch {
    return false;
  }
};

/** Remember the choice. Returns false when the browser is not keeping data (the reader is then asked again next time). */
export function giveMicConsent(storage = safeStorage()) {
  try {
    if (!storage) return false;
    storage.setItem(CONSENT_KEY, "yes");
    return true;
  } catch {
    return false;
  }
}

export function withdrawMicConsent(storage = safeStorage()) {
  try {
    storage?.removeItem(CONSENT_KEY);
    return true;
  } catch {
    return false;
  }
}
