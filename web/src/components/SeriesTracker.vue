<script setup>
// Progress of a long document that is being created as several linked parts, one after another.
import { computed, useId } from "vue";
import { STEPS, friendlyJobError } from "../jobSteps.js";

const props = defineProps({ jobs: { type: Array, required: true }, title: { type: String, default: "" } });
const headId = useId();
const total = computed(() => props.jobs.length);
const ready = computed(() => props.jobs.filter((j) => j.status === "done").length);
const failed = computed(() => props.jobs.filter((j) => j.status === "failed").length);
const finished = computed(() => ready.value + failed.value === total.value);
const first = computed(() => props.jobs.find((j) => j.status === "done" && j.passageId));
const current = computed(() => props.jobs.find((j) => j.status !== "done" && j.status !== "failed"));

function label(job) {
  if (job.status === "done") return "Ready";
  if (job.status === "failed") return "Could not be created";
  if (job === current.value && job.status === "running") return STEPS.find((s) => s.key === job.step)?.hint ?? "Working";
  return "Waiting";
}
const href = (job) => `#/read/${encodeURIComponent(job.passageId)}`;
</script>

<template>
  <section class="card tracker" :aria-labelledby="headId">
    <div class="head">
      <h3 :id="headId">{{ title }}</h3>
      <span class="count num">{{ ready }} of {{ total }} parts ready</span>
    </div>
    <progress class="bar" :max="total" :value="ready" :aria-label="`${ready} of ${total} parts ready`"></progress>
    <p v-if="!finished" class="small muted" role="status">
      A long document is created one part at a time. You can start reading as soon as the first part is ready, and this page updates by itself.
    </p>
    <ol class="parts">
      <li v-for="(job, n) in jobs" :key="job.id" :class="job.status">
        <span class="name">Part {{ n + 1 }}</span>
        <span class="state small" :class="{ muted: job.status !== 'failed' }">{{ label(job) }}</span>
        <a v-if="job.status === 'done' && job.passageId" class="btn" :href="href(job)">Open</a>
        <span v-if="job.status === 'failed'" class="small error-text" role="alert">{{ friendlyJobError(job.error) }}</span>
      </li>
    </ol>
    <div v-if="finished" class="result" role="status">
      <p v-if="!failed" class="notice ok"><strong>All {{ total }} parts are ready.</strong> They are linked, so each part has a button to the next. Find the whole document in the Library.</p>
      <p v-else class="notice warn">{{ ready }} of {{ total }} parts are ready; {{ failed }} could not be created. The ready parts are in the Library. You can add the document again to retry.</p>
      <a v-if="first" class="btn primary" :href="href(first)">Open the first ready part</a>
    </div>
  </section>
</template>

<style scoped>
.tracker { display: grid; gap: var(--s2); }
.head { display: flex; justify-content: space-between; gap: var(--s2); flex-wrap: wrap; align-items: baseline; }
.count { color: var(--muted); font-size: 14px; }
.bar { width: 100%; height: 12px; accent-color: var(--primary); }
.parts { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.parts li { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface-2); }
.parts li.running { border-color: var(--primary); background: var(--primary-soft); }
.parts li.failed { border-color: var(--danger); background: var(--danger-soft); }
.name { font-weight: 700; min-width: 64px; }
.state { flex: 1 1 160px; }
.result { display: grid; gap: var(--s1); justify-items: start; }
</style>
