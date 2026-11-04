// Maps a backend Job to the 5-step progress tracker. The passage is added to the library only after the last step.
export const STEPS = [
  { key: "parse", label: "Read", hint: "Split the text into words and sentences" },
  { key: "synthesize", label: "Voice", hint: "Create the narration audio" },
  { key: "align", label: "Match", hint: "Match each word to its sound" },
  { key: "publish", label: "Save", hint: "Save the narration" },
  { key: "translate", label: "Translate", hint: "Make the other-language version, then add both to the library" },
];

/** Returns [{key,label,hint,state}] where state is done | current | pending | failed. */
export function stepStates(job) {
  if (!job) return STEPS.map((s) => ({ ...s, state: "pending" }));
  const idx = job.step === "done" ? STEPS.length : STEPS.findIndex((s) => s.key === job.step);
  const current = idx < 0 ? 0 : idx;
  return STEPS.map((s, n) => {
    if (job.status === "done" || n < current) return { ...s, state: "done" };
    if (n === current) return { ...s, state: job.status === "failed" ? "failed" : "current" };
    return { ...s, state: "pending" };
  });
}

export const isFinished = (job) => Boolean(job) && (job.status === "done" || job.status === "failed");

/** Whole seconds between start and finish (or `now`). */
export function elapsedSeconds(startedAt, finishedAt, now = Date.now()) {
  const start = Date.parse(startedAt);
  if (Number.isNaN(start)) return null;
  const end = finishedAt ? Date.parse(finishedAt) : now;
  return Math.max(0, Math.round(((Number.isNaN(end) ? now : end) - start) / 1000));
}

/**
 * Progress of a long text, which is narrated in several stretches inside one job: { done, total, percent, remainingSeconds }, or null for an ordinary job.
 * The time left is the elapsed time per finished stretch times the stretches that remain (null until the first one is finished).
 */
export function longProgress(job, now = Date.now()) {
  const total = Number(job?.chunksTotal) || 0;
  if (!total) return null;
  const done = Math.min(Number(job.chunksDone) || 0, total);
  const finished = job.status === "done";
  const elapsed = elapsedSeconds(job.startedAt, job.finishedAt, now) ?? 0;
  const remainingSeconds = finished ? 0 : done > 0 ? Math.max(5, Math.round((elapsed / done) * (total - done))) : null;
  return { done: finished ? total : done, total, percent: finished ? 100 : Math.min(99, Math.round((done / total) * 100)), remainingSeconds };
}

/** "about 4 minutes left", "less than a minute left", or "" when the time is not known yet. */
export function timeLeftText(seconds) {
  if (seconds === null || seconds === undefined) return "";
  if (seconds < 60) return "less than a minute left";
  const minutes = Math.round(seconds / 60);
  return minutes < 90 ? `about ${minutes} minute${minutes === 1 ? "" : "s"} left` : `about ${Math.round(minutes / 6) / 10} hours left`;
}

const GENERIC_FAILURE = "We could not finish creating the audio. Please try again in a moment.";
// Anything that looks like an internal detail (file paths, error codes, stack traces, URLs, endpoints) is never shown to a person.
const INTERNAL = /(\/api\/|https?:\/\/|\bE[A-Z]{3,}\b|errno|Traceback|\bat [\w$.<>]+ \(|\.(py|js|mjs|json)\b|\bHTTP \d{3}\b|\b(Lambda|DynamoDB|S3|Bedrock|Step Functions|stderr|stdout|exit code)\b|[A-Za-z]:\\|\/(usr|var|opt|tmp|home)\/)/i;

/** The failure message for a job, or a generic one when the server's text could reveal how the service works. */
export function friendlyJobError(error) {
  const text = typeof error === "string" ? error.trim() : "";
  return text && text.length <= 240 && !INTERNAL.test(text) ? text : GENERIC_FAILURE;
}
