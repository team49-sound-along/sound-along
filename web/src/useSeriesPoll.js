import { computed, onBeforeUnmount, ref } from "vue";
import { api } from "./api.js";
import { isFinished } from "./jobSteps.js";

const POLL_MS = 2000;
const MAX_POLL_FAILURES = 5;

/** Tracks the jobs of a long document (one per part). Polls the parts that are not finished until every part is. */
export function useSeriesPoll() {
  const jobs = ref([]);
  const pollError = ref("");
  const running = computed(() => jobs.value.length > 0 && jobs.value.some((j) => !isFinished(j)));
  let timer = 0;
  let alive = true;
  let run = 0;

  onBeforeUnmount(() => {
    alive = false;
    clearTimeout(timer);
  });

  async function tick(mine, failures = 0) {
    if (!alive || mine !== run) return;
    const open = jobs.value.filter((j) => !isFinished(j));
    if (!open.length) return;
    let failed = false;
    await Promise.all(
      open.map(async (j) => {
        try {
          const next = await api.job(j.id);
          if (mine !== run) return;
          jobs.value = jobs.value.map((x) => (x.id === next.id ? next : x));
        } catch {
          failed = true;
        }
      }),
    );
    if (!alive || mine !== run) return;
    if (failed) {
      if (failures + 1 >= MAX_POLL_FAILURES) {
        pollError.value = "We lost the connection while checking progress. Your audio may still be on its way: check your connection, then refresh this page.";
        return;
      }
      timer = setTimeout(() => tick(mine, failures + 1), POLL_MS);
      return;
    }
    pollError.value = "";
    if (jobs.value.some((j) => !isFinished(j))) timer = setTimeout(() => tick(mine, 0), POLL_MS);
  }

  function start(jobIds, title) {
    clearTimeout(timer);
    run += 1;
    pollError.value = "";
    const total = jobIds.length;
    jobs.value = jobIds.map((id, i) => ({
      id, title: `${title} (Part ${i + 1} of ${total})`, status: "queued", step: "parse", passageId: null, humanPassageId: null,
      error: null, metrics: null, startedAt: new Date().toISOString(), finishedAt: null,
    }));
    tick(run);
  }

  function reset() {
    clearTimeout(timer);
    run += 1;
    jobs.value = [];
    pollError.value = "";
  }

  return { jobs, pollError, running, start, reset };
}
