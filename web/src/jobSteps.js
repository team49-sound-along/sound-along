// Maps a backend Job to the 4-step progress tracker.
export const STEPS = [
  { key: "parse", label: "Parse", hint: "Split text into words and sentences" },
  { key: "synthesize", label: "Synthesize", hint: "Generate the narration audio" },
  { key: "align", label: "Align", hint: "Verify word-level timing" },
  { key: "publish", label: "Publish", hint: "Make it available in the reader" },
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
