// Thin wrapper over the browser's built-in speech recognition (SpeechRecognition / webkitSpeechRecognition). No DOM or Vue.
//
// PRIVACY: Chrome, Edge and Safari send the microphone audio to the browser maker's speech service while this runs, so the panel says so in a short
// line and the browser asks for the microphone itself. The wrapper itself keeps nothing: it only passes transcripts on as { id, transcript, isFinal }.
// Chrome stops listening after a few seconds of silence, so the wrapper starts a new session by itself until stop() is called. Each session
// numbers its results in its own range, so a transcript id never repeats and the follower (readAloud.js) keeps its place across restarts.

const SESSION_SPAN = 10_000;
const RESTART_DELAY_MS = 250;
const MAX_SILENT_SESSIONS = 3; // this many sessions in a row with no speech: stop and ask the reader to check the microphone

export const getRecognitionCtor = (win = globalThis) => win?.SpeechRecognition ?? win?.webkitSpeechRecognition ?? null;
export const recognitionSupported = (win = globalThis) => typeof getRecognitionCtor(win) === "function";
export const recognitionLang = (language) => (language === "es" ? "es-US" : "en-US");

const MESSAGES = {
  "not-allowed": "The microphone is blocked. Allow the microphone for this site in your browser settings, then try again.",
  "service-not-allowed": "This browser is not allowing speech recognition. Check the browser or device settings, then try again.",
  "audio-capture": "No microphone was found. Plug one in or check that it is turned on, then try again.",
  network: "Speech recognition needs an internet connection and could not connect. Check your connection, then try again. You can still read along with the audio.",
  "language-not-supported": "This browser cannot listen for this language. You can still read along with the audio.",
  "no-speech": "We could not hear anything. Check that your microphone is on and close to you, then press Start again.",
  generic: "Listening stopped unexpectedly. Press Start to try again.",
};
const QUIET_CODES = new Set(["no-speech", "aborted"]); // normal events: a new session starts, nothing to show yet

/** Friendly text for a recognition error code, and whether listening has to stop. */
export function describeError(code) {
  const quiet = QUIET_CODES.has(code);
  return { code: code || "unknown", message: MESSAGES[code] ?? MESSAGES.generic, fatal: !quiet };
}

/**
 * @param {{ language: string, onResult: Function, onStatus?: Function, onError?: Function, Ctor?: Function, setTimer?: Function, clearTimer?: Function }} options
 * @returns {{ start: () => boolean, stop: () => void, isRunning: () => boolean }}
 */
export function createRecognizer({ language, onResult, onStatus = () => {}, onError = () => {}, Ctor = getRecognitionCtor(), setTimer = setTimeout, clearTimer = clearTimeout }) {
  let wanted = false;
  let session = 0;
  let current = null;
  let timer = null;
  let silentSessions = 0;
  let heardSpeech = false;
  let open = new Map(); // interim transcripts of the current session, flushed as final when the session ends

  const fail = (code) => {
    const info = describeError(code);
    wanted = false;
    clearTimer(timer);
    onError(info);
    onStatus("idle");
  };

  // Every handler belongs to one recognizer instance and acts only while that instance is the current one, so a late event from a
  // stopped or replaced recognizer can never touch the next session.
  function handleResult(rec, token, event) {
    if (current !== rec) return;
    heardSpeech = true;
    silentSessions = 0;
    for (let i = event.resultIndex ?? 0; i < event.results.length; i += 1) {
      const res = event.results[i];
      const id = token * SESSION_SPAN + i;
      const transcript = String(res?.[0]?.transcript ?? "");
      if (res?.isFinal) open.delete(id);
      else open.set(id, transcript);
      onResult({ id, transcript, isFinal: Boolean(res?.isFinal) });
    }
  }

  function flushOpen() {
    open.forEach((transcript, id) => onResult({ id, transcript, isFinal: true })); // a session ended mid-sentence: keep what was heard
    open = new Map();
  }

  function detach(rec) {
    rec.onresult = null;
    rec.onend = null;
    rec.onerror = null;
    rec.onstart = null;
  }

  function handleEnd(rec, token) {
    if (current !== rec) return;
    flushOpen();
    detach(rec);
    current = null;
    if (!wanted) {
      onStatus("idle");
      return;
    }
    if (!heardSpeech) silentSessions += 1;
    if (silentSessions >= MAX_SILENT_SESSIONS) {
      fail("no-speech");
      return;
    }
    onStatus("restarting");
    timer = setTimer(() => {
      if (token === session && wanted && !current) begin();
    }, RESTART_DELAY_MS);
  }

  function begin() {
    if (!wanted) return;
    session += 1;
    const token = session;
    heardSpeech = false;
    try {
      const rec = new Ctor();
      rec.continuous = true;
      rec.interimResults = true;
      rec.maxAlternatives = 1;
      rec.lang = recognitionLang(language);
      rec.onstart = () => {
        if (current === rec) onStatus("listening");
      };
      rec.onresult = (event) => handleResult(rec, token, event);
      rec.onerror = (event) => {
        if (current !== rec) return;
        const info = describeError(event?.error);
        if (info.fatal) fail(event?.error);
      };
      rec.onend = () => handleEnd(rec, token);
      current = rec;
      rec.start();
    } catch {
      current = null;
      fail("generic");
    }
  }

  return {
    start() {
      if (!Ctor) {
        fail("service-not-allowed");
        return false;
      }
      if (wanted) return true;
      wanted = true;
      silentSessions = 0;
      onStatus("starting");
      begin();
      return true;
    },
    stop() {
      wanted = false;
      clearTimer(timer);
      const old = current;
      current = null;
      if (old) {
        flushOpen();
        detach(old);
        try {
          old.stop();
        } catch {
          // already stopped
        }
      }
      onStatus("idle");
    },
    isRunning: () => wanted,
  };
}
