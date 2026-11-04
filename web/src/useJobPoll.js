import { computed, onBeforeUnmount, ref } from "vue";
import { api } from "./api.js";
import { isFinished } from "./jobSteps.js";

const POLL_MS = 1000;
const MAX_POLL_FAILURES = 5;

/** Tracks one generation job: polls GET /api/jobs/:id once a second and keeps an elapsed-time clock. */
export function useJobPoll() {
  const job = ref(null);
  const pollError = ref("");
  const now = ref(Date.now());
  const running = computed(() => job.value !== null && !isFinished(job.value));
  let timer = 0;
  let clock = 0;
  let alive = true;
  let run = 0;

  function stop() {
    clearTimeout(timer);
    clearInterval(clock);
  }
  onBeforeUnmount(() => {
    alive = false;
    stop();
  });

  async function poll(jobId, mine, failures = 0) {
    if (!alive || mine !== run) return;
    try {
      const next = await api.job(jobId);
      if (!alive || mine !== run) return;
      job.value = next;
      pollError.value = "";
      if (isFinished(next)) return clearInterval(clock);
      timer = setTimeout(() => poll(jobId, mine, 0), POLL_MS);
    } catch (e) {
      if (!alive || mine !== run) return;
      if (failures + 1 >= MAX_POLL_FAILURES) {
        clearInterval(clock);
        pollError.value = "We lost the connection while checking progress. Your audio may still be on its way: check your connection, then refresh this page.";
        return;
      }
      timer = setTimeout(() => poll(jobId, mine, failures + 1), POLL_MS);
    }
  }

  function start(jobId, title) {
    stop();
    run += 1;
    pollError.value = "";
    now.value = Date.now();
    clock = setInterval(() => (now.value = Date.now()), 1000);
    job.value = { id: jobId, title, status: "queued", step: "parse", passageId: null, humanPassageId: null, error: null, metrics: null, startedAt: new Date().toISOString(), finishedAt: null };
    poll(jobId, run);
  }

  function reset() {
    stop();
    run += 1;
    job.value = null;
    pollError.value = "";
  }

  return { job, now, pollError, running, start, reset };
}
