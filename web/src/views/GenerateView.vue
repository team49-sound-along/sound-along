<script setup>
import { computed, ref } from "vue";
import JobTracker from "../components/JobTracker.vue";
import TextFileDrop from "../components/TextFileDrop.vue";
import RecordingPicker from "../components/RecordingPicker.vue";
import { api } from "../api.js";
import { useJobPoll } from "../useJobPoll.js";
import { validateRecording } from "../files.js";
import { uploadRecording } from "../upload.js";
import { TEXT_MAX, TEXT_MIN, TITLE_MAX, generateErrorMessage, validateGenerate } from "../validation.js";
import { formatCount } from "../format.js";

const title = ref("");
const text = ref("");
const recording = ref(null);
const submitted = ref(false);
const starting = ref(false);
const uploadPct = ref(null);
const startError = ref("");
const { job, now, pollError, running: jobRunning, start, reset: resetJob } = useJobPoll();

const check = computed(() => validateGenerate({ title: title.value, text: text.value }));
const running = computed(() => starting.value || jobRunning.value);
const overLimit = computed(() => text.value.length > TEXT_MAX);

function onFileLoaded(f) {
  title.value = f.title;
  text.value = f.text;
}

async function submit() {
  submitted.value = true;
  startError.value = "";
  if (!check.value.valid || running.value) return;
  starting.value = true;
  resetJob();
  try {
    const body = { title: title.value.trim(), text: text.value };
    if (recording.value) {
      const file = recording.value;
      const { contentType } = validateRecording(file);
      uploadPct.value = 0;
      const { recordingId, upload } = await api.createRecording({ filename: file.name, contentType, size: file.size });
      await uploadRecording(file, upload, (p) => (uploadPct.value = p));
      body.recordingId = recordingId;
    }
    const { jobId } = await api.generate(body);
    start(jobId, body.title);
  } catch (e) {
    startError.value = generateErrorMessage(e.status, e.message);
  } finally {
    starting.value = false;
    uploadPct.value = null;
  }
}

function reset() {
  title.value = "";
  text.value = "";
  recording.value = null;
  submitted.value = false;
  startError.value = "";
  resetJob();
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>Generate</h2>
        <p>Paste a passage or add a text file. Sound Along creates the narration and the word-by-word timing automatically. You can also add your own recording of the passage.</p>
      </div>
    </div>

    <form class="card form" novalidate @submit.prevent="submit">
      <TextFileDrop :disabled="running" @loaded="onFileLoaded" />
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
      <RecordingPicker v-model:file="recording" :disabled="running" />
      <div v-if="uploadPct !== null" class="small" role="status">
        <label for="g-up">Uploading recording: {{ uploadPct }}%</label>
        <progress id="g-up" class="bar" max="100" :value="uploadPct"></progress>
      </div>
      <p v-if="startError" class="notice error" role="alert">{{ startError }}</p>
      <div class="actions">
        <button class="btn primary" type="submit" :disabled="running">{{ uploadPct !== null ? "Uploading..." : running ? "Generating..." : "Generate audio and timing" }}</button>
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
.bar { width: 100%; height: 12px; accent-color: var(--primary); }
</style>
