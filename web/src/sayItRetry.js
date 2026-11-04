// "Say it with me": a short guided retry for one word. Pure state machine plus a judge; the screen supplies audio and microphone.
// idle -> slow (word played slowly) -> listening (microphone on) -> success | retry (one more try) -> moveOn after the second miss.
// It never blocks: every phase has a way out, a miss is never scored, and a microphone problem ends it quietly.
import { createReadAlong, feed } from "./readAloud.js";

export const MAX_TRIES = 2;

export const initial = () => ({ phase: "idle", tries: 0, message: "" });

const listenOrSlow = (state, canSlow) => ({ ...state, phase: canSlow ? "slow" : "listening", message: "" });

/** @param event { type: start|tryAgain (with canSlow), slowEnded, heard, missed, failed (with message), stop, reset } */
export function step(state, event) {
  const s = state ?? initial();
  switch (event?.type) {
    case "start":
      return listenOrSlow({ ...initial() }, event.canSlow === true);
    case "tryAgain":
      return s.phase === "retry" ? listenOrSlow(s, event.canSlow === true) : s;
    case "slowEnded":
      return s.phase === "slow" ? { ...s, phase: "listening" } : s;
    case "heard":
      return s.phase === "listening" ? { ...s, phase: "success", tries: s.tries + 1 } : s;
    case "missed": {
      if (s.phase !== "listening") return s;
      const tries = s.tries + 1;
      return { ...s, phase: tries >= MAX_TRIES ? "moveOn" : "retry", tries };
    }
    case "failed":
      return s.phase === "idle" ? s : { ...s, phase: "unavailable", message: String(event.message ?? "") };
    case "stop":
      return { ...s, phase: "idle", message: "" };
    case "reset":
      return initial();
    default:
      return s;
  }
}

/** The "missed" countdown begins when the microphone is really on (after any permission prompt), never before, and only once per try. */
export const shouldArmMissTimer = (recognizerStatus, alreadyArmed) => recognizerStatus === "listening" && !alreadyArmed;

export const listensNow =(state) => state?.phase === "listening";
export const finished = (state) => ["success", "moveOn", "unavailable"].includes(state?.phase);

/**
 * Did the learner say this word? Reuses the read-along follower with the word as the whole passage, so spelling and accent leniency,
 * numbers and filler words behave exactly as in the main reading. Returns "match", "miss", or "pending" (an interim result that is not
 * a match yet: the speech may still be going).
 */
export function judge(transcript, wordText, language, isFinal) {
  const follower = createReadAlong([{ text: String(wordText ?? "") }], { language });
  if (follower.targets.length === 0 || typeof transcript !== "string") return "miss";
  const { events } = feed(follower, { id: 0, transcript, isFinal: isFinal === true });
  if (events.some((e) => e.type === "done")) return "match";
  return isFinal === true ? "miss" : "pending";
}
