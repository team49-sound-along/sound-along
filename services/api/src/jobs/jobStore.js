import { randomUUID } from "node:crypto";

const MAX_KEPT = 200;

/** In-memory job registry. Jobs are short-lived; in AWS this is a Step Functions execution. */
export function createJobStore() {
  const jobs = new Map();

  const snapshot = (job) => ({ ...job });

  return {
    create(title) {
      const job = {
        id: randomUUID(),
        title,
        status: "queued",
        step: "parse",
        passageId: null,
        error: null,
        metrics: null,
        startedAt: new Date().toISOString(),
        finishedAt: null,
      };
      jobs.set(job.id, job);
      if (jobs.size > MAX_KEPT) jobs.delete(jobs.keys().next().value);
      return snapshot(job);
    },
    get(id) {
      const job = jobs.get(id);
      return job ? snapshot(job) : null;
    },
    update(id, patch) {
      const current = jobs.get(id);
      if (!current) return null;
      const next = { ...current, ...patch };
      jobs.set(id, next);
      return snapshot(next);
    },
    activeCount() {
      return [...jobs.values()].filter((j) => j.status === "queued" || j.status === "running").length;
    },
  };
}
