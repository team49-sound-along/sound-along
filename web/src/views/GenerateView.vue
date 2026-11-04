<script setup>
import { computed, ref, watch } from "vue";
import JobTracker from "../components/JobTracker.vue";
import TextFileDrop from "../components/TextFileDrop.vue";
import RecordingPicker from "../components/RecordingPicker.vue";
import { api } from "../api.js";
import { useJobPoll } from "../useJobPoll.js";
import { useSeriesPoll } from "../useSeriesPoll.js";
import SeriesTracker from "../components/SeriesTracker.vue";
import { describeSize } from "../documentSize.js";
import { validateRecording } from "../files.js";
import { uploadRecording } from "../upload.js";
import { TEXT_MAX, TEXT_MIN, TITLE_MAX, generateErrorMessage, validateGenerate } from "../validation.js";
import { LANGUAGES, PRONUNCIATION_NOTE, langAttr, languageCopy, withLanguage } from "../language.js";
import { formatCount } from "../format.js";
import { guessLanguage } from "../languageGuess.js";
import { analyzeMix, keepLanguage } from "../languageMix.js";
import LanguageMixNotice from "../components/LanguageMixNotice.vue";

const title = ref("");
const text = ref("");
const language = ref("en");
const autoLanguageNote = ref("");
const textBeforeKeep = ref(null);
const mix = computed(() => analyzeMix(text.value));
function keepOnly(lang) {
  textBeforeKeep.value = text.value;
  text.value = keepLanguage(text.value, lang);
  language.value = lang;
}
function undoKeep() {
  if (textBeforeKeep.value !== null) text.value = textBeforeKeep.value;
  textBeforeKeep.value = null;
}
// Pasted Spanish text with English selected (or the reverse) would be read by the wrong voice, so the language follows the text when it is clear.
watch(text, (value) => {
  const guess = guessLanguage(value);
  if (guess && guess !== language.value) {
    language.value = guess;
    autoLanguageNote.value = `We set the language to ${guess === "es" ? "Spanish" : "English"} to match your text.`;
  }
});
const copy = computed(() => languageCopy(language.value));
const recording = ref(null);
const submitted = ref(false);
const starting = ref(false);
const uploadPct = ref(null);
const startError = ref("");
const { job, now, pollError, running: jobRunning, start, reset: resetJob } = useJobPoll();
const series = useSeriesPoll();
const seriesTitle = ref("");
const size = computed(() => describeSize(text.value));

const check = computed(() => validateGenerate({ title: title.value, text: text.value }));
const running = computed(() => starting.value || jobRunning.value || series.running.value);
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
  series.reset();
  try {
    const body = withLanguage({ title: title.value.trim(), text: text.value }, language.value);
    if (recording.value) {
      const file = recording.value;
      const { contentType } = validateRecording(file);
      uploadPct.value = 0;
      const { recordingId, upload } = await api.createRecording({ filename: file.name, contentType, size: file.size });
      await uploadRecording(file, upload, (p) => (uploadPct.value = p));
      body.recordingId = recordingId;
    }
    const { jobId, jobIds } = await api.generate(body);
    if (jobIds?.length > 1) {
      seriesTitle.value = body.title;
      series.start(jobIds, body.title);
    } else {
      start(jobId, body.title);
    }
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
  language.value = "en";
  autoLanguageNote.value = "";
  submitted.value = false;
  startError.value = "";
  resetJob();
  series.reset();
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
        <label for="g-lang">Language</label>
        <select id="g-lang" v-model="language" class="input" aria-describedby="g-lang-help" :disabled="running">
          <option v-for="l in LANGUAGES" :key="l.value" :value="l.value">{{ l.label }}</option>
        </select>
        <p id="g-lang-help" class="small muted">{{ PRONUNCIATION_NOTE }}<template v-if="language === 'es'"> {{ copy.help }}</template></p>
        <p v-if="autoLanguageNote" class="small" role="status">{{ autoLanguageNote }}</p>
      </div>
      <div class="field">
        <label for="g-title">Title</label>
        <input id="g-title" v-model="title" class="input" :lang="langAttr(language)" :placeholder="copy.titlePlaceholder" type="text" :maxlength="TITLE_MAX + 20" autocomplete="off" :aria-invalid="submitted && !!check.errors.title" :aria-describedby="submitted && check.errors.title ? 'g-title-err' : undefined" :disabled="running" />
        <span v-if="submitted && check.errors.title" id="g-title-err" class="error-text">{{ check.errors.title }}</span>
      </div>
      <div class="field">
        <label for="g-text">{{ copy.textLabel }}</label>
        <LanguageMixNotice v-if="!running" :mix="mix" :can-undo="textBeforeKeep !== null && !mix.mixed" @keep="keepOnly" @undo="undoKeep" />
        <textarea id="g-text" v-model="text" class="input" :lang="langAttr(language)" :placeholder="copy.textPlaceholder" :aria-invalid="submitted && !!check.errors.text" aria-describedby="g-count g-text-err" :disabled="running"></textarea>
        <div class="count-row">
          <span id="g-text-err" class="error-text">{{ submitted ? check.errors.text : "" }}</span>
          <span id="g-count" class="small num" :class="overLimit || size.tooLong ? 'error-text' : 'muted'">{{ formatCount(size.words) }} words &middot; {{ formatCount(text.length) }} / {{ formatCount(TEXT_MAX) }} characters (minimum {{ TEXT_MIN }})</span>
        <span v-if="size.parts > 1 && !size.tooLong" class="small" role="status">This is a long document. It will be created as about {{ size.parts }} linked parts of up to 1,000 words, so each can be read and assigned on its own.</span>
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
        <button v-if="(job || series.jobs.value.length) && !running" class="btn" type="button" @click="reset">Start another</button>
      </div>
    </form>

    <p v-if="pollError || series.pollError.value" class="notice error" role="alert">{{ pollError || series.pollError.value }}</p>
    <JobTracker v-if="job" :job="job" :now="now" />
    <SeriesTracker v-if="series.jobs.value.length" :jobs="series.jobs.value" :title="seriesTitle" />
  </div>
</template>

<style scoped>
.form { display: grid; gap: var(--s2); }
.count-row { display: flex; justify-content: space-between; gap: var(--s2); flex-wrap: wrap; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
.bar { width: 100%; height: 12px; accent-color: var(--primary); }
</style>
