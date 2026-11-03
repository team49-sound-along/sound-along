<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
import JobTracker from "../components/JobTracker.vue";
import { api } from "../api.js";
import { isFinished } from "../jobSteps.js";
import { TEXT_MAX, TEXT_MIN, TITLE_MAX, generateErrorMessage, validateGenerate } from "../validation.js";
import { formatCount } from "../format.js";

const POLL_MS = 1000;
const MAX_POLL_FAILURES = 5;

const title = ref("");
const text = ref("");
const submitted = ref(false);
const starting = ref(false);
const startError = ref("");
const job = ref(null);
const pollError = ref("");
const now = ref(Date.now());
let timer = 0;
let clock = 0;
let alive = true;

const check = computed(() => validateGenerate({ title: title.value, text: text.value }));
const running = computed(() => starting.value || (job.value !== null && !isFinished(job.value)));
const overLimit = computed(() => text.value.length > TEXT_MAX);

onBeforeUnmount(() => {
  alive = false;
  clearTimeout(timer);
  clearInterval(clock);
});

async function poll(jobId, failures = 0) {
  if (!alive) return;
  try {
    job.value = await api.job(jobId);
    pollError.value = "";
    if (isFinished(job.value)) return clearInterval(clock);
    timer = setTimeout(() => poll(jobId, 0), POLL_MS);
  } catch (e) {
    if (failures + 1 >= MAX_POLL_FAILURES) {
      clearInterval(clock);
      pollError.value = `Lost contact with the server while checking progress. ${e.message}`;
      return;
    }
    timer = setTimeout(() => poll(jobId, failures + 1), POLL_MS);
  }
}

async function submit() {
  submitted.value = true;
  startError.value = "";
  if (!check.value.valid || running.value) return;
  starting.value = true;
  job.value = null;
  pollError.value = "";
  try {
    const { jobId } = await api.generate({ title: title.value.trim(), text: text.value });
    now.value = Date.now();
    clearInterval(clock);
    clock = setInterval(() => (now.value = Date.now()), 1000);
    job.value = { id: jobId, title: title.value.trim(), status: "queued", step: "parse", passageId: null, error: null, metrics: null, startedAt: new Date().toISOString(), finishedAt: null };
    poll(jobId);
  } catch (e) {
    startError.value = generateErrorMessage(e.status, e.message);
  } finally {
    starting.value = false;
  }
}

function reset() {
  title.value = "";
  text.value = "";
  submitted.value = false;
  job.value = null;
  pollError.value = "";
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>Generate</h2>
        <p>Paste any passage. Sound Along creates the narration and the word-by-word timing automatically, with no manual recording or alignment.</p>
      </div>
    </div>

    <form class="card form" novalidate @submit.prevent="submit">
      <div class="field">
        <label for="g-title">Title</label>
        <input id="g-title" v-model="title" class="input" type="text" :maxlength="TITLE_MAX + 20" autocomplete="off" :aria-invalid="submitted && !!check.errors.title" :aria-describedby="submitted && check.errors.title ? 'g-title-err' : undefined" :disabled="running" />
        <span v-if="submitted && check.errors.title" id="g-title-err" class="error-text">{{ check.errors.title }}</span>
      </div>
      <div class="field">
        <label for="g-text">Passage text</label>
        <textarea id="g-text" v-model="text" class="input" :aria-invalid="submitted && !!check.errors.text" aria-describedby="g-count g-text-err" :disabled="running"></textarea>
        <div class="count-row">
          <span id="g-text-err" class="error-text">{{ submitted ? check.errors.text : "" }}</span>
          <span id="g-count" class="small num" :class="overLimit ? 'error-text' : 'muted'">{{ formatCount(text.length) }} / {{ formatCount(TEXT_MAX) }} characters (minimum {{ TEXT_MIN }})</span>
        </div>
      </div>
      <p v-if="startError" class="notice error" role="alert">{{ startError }}</p>
      <div class="actions">
        <button class="btn primary" type="submit" :disabled="running">{{ running ? "Generating..." : "Generate audio and timing" }}</button>
        <button v-if="job && !running" class="btn" type="button" @click="reset">Start another</button>
      </div>
    </form>

    <p v-if="pollError" class="notice error" role="alert">{{ pollError }}</p>
    <JobTracker v-if="job" :job="job" :now="now" />
  </div>
</template>

<style scoped>
.form { display: grid; gap: var(--s2); }
.count-row { display: flex; justify-content: space-between; gap: var(--s2); flex-wrap: wrap; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
