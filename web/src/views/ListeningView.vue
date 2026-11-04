<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
import StateBlock from "../components/StateBlock.vue";
import ClipPlayer from "../components/ClipPlayer.vue";
import RadioGroup from "../components/RadioGroup.vue";
import { api } from "../api.js";
import { PREFERENCES, completedLabel, emptyAnswer, getRaterId, isComplete, isUsableTrial, ratingErrorMessage, ratingPayload, trialLoadMessage } from "../listening.js";

const trial = ref(null);
const loading = ref(true);
const loadError = ref("");
const answer = ref(emptyAnswer());
const submitting = ref(false);
const submitError = ref("");
const thanks = ref("");
const completed = ref(0);
const clipA = ref(null);
const clipB = ref(null);
const heading = ref(null);
let alive = true;
let seq = 0;

const ready = computed(() => isComplete(answer.value) && !submitting.value);
const empty = computed(() => !loading.value && !loadError.value && !trial.value);

function stopAudio() {
  clipA.value?.stop();
  clipB.value?.stop();
}

async function loadTrial() {
  const mine = ++seq;
  stopAudio();
  loading.value = true;
  loadError.value = "";
  try {
    const t = await api.ratingTrial();
    if (!alive || mine !== seq) return;
    trial.value = isUsableTrial(t) ? t : null;
    answer.value = emptyAnswer();
  } catch (e) {
    if (alive && mine === seq) {
      trial.value = null;
      loadError.value = trialLoadMessage(e.status, e.message);
    }
  } finally {
    if (alive && mine === seq) loading.value = false;
  }
}

async function submit() {
  if (!ready.value || !trial.value) return;
  submitting.value = true;
  submitError.value = "";
  try {
    let storage;
    try { storage = localStorage; } catch { storage = undefined; }
    await api.submitRating(ratingPayload(trial.value, answer.value, getRaterId(storage)));
    completed.value += 1;
    thanks.value = "Thank you. Your rating was saved. Here is the next pair.";
    await loadTrial();
    heading.value?.focus();
  } catch (e) {
    submitError.value = ratingErrorMessage(e.status, e.message);
  } finally {
    submitting.value = false;
  }
}

onBeforeUnmount(() => {
  alive = false;
  stopAudio();
});
loadTrial();
</script>

<template>
  <div class="page narrow">
    <div class="page-head">
      <div>
        <h2 ref="heading" tabindex="-1">Listening test</h2>
        <p>You will hear two short readings of the same text. Neither one is labeled. Rate how natural each sounds for reading along. There are no right answers, so go with what you hear.</p>
      </div>
      <p class="badge teal num" role="status" aria-live="polite">{{ completedLabel(completed) }}</p>
    </div>

    <p class="sr-only" role="status" aria-live="polite">{{ thanks }}</p>
    <p v-if="thanks && !loading" class="notice ok">{{ thanks }}</p>

    <StateBlock :loading="loading" :error="loadError" :empty="empty" loading-label="Loading a listening clip" empty-title="No listening clips yet." empty-text="Run scripts/build_samples.py." @retry="loadTrial">
      <form v-if="trial" class="stack" novalidate @submit.prevent="submit">
        <div class="card">
          <p class="eyebrow">Text</p>
          <h3>{{ trial.title }}</h3>
          <p v-if="trial.prompt" class="muted">{{ trial.prompt }}</p>
        </div>
        <div class="clips">
          <ClipPlayer ref="clipA" id="clip-a" label="Reading A" :url="trial.a.url" v-model:rating="answer.ratingA" :disabled="submitting" />
          <ClipPlayer ref="clipB" id="clip-b" label="Reading B" :url="trial.b.url" v-model:rating="answer.ratingB" :disabled="submitting" />
        </div>
        <div class="card">
          <RadioGroup legend="Which did you prefer?" name="preferred" :options="PREFERENCES" v-model="answer.preferred" :disabled="submitting" inline />
        </div>
        <p v-if="submitError" class="notice error" role="alert">{{ submitError }}</p>
        <div class="actions">
          <button class="btn primary" type="submit" :disabled="!ready" :aria-describedby="ready ? undefined : 'l-need'">{{ submitting ? "Saving..." : "Submit rating" }}</button>
          <span v-if="!ready && !submitting" id="l-need" class="small muted">Rate both readings and choose a preference to submit.</span>
        </div>
      </form>
    </StateBlock>
  </div>
</template>

<style scoped>
.stack { display: grid; gap: var(--s2); min-width: 0; }
.clips { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(340px, 100%), 1fr)); gap: var(--s2); }
.clips > * { min-width: 0; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s2); }
h2:focus { outline: none; }
</style>
