<script setup>
// "Read aloud with the microphone": the learner reads the passage, the panel follows word by word and stops with a plain explanation when a
// word is skipped or clearly heard as a different word. Logic lives in readAloud.js (follower) and speechRecognizer.js (browser speech
// recognition); this file only wires them to the screen. The reader draws the marks this panel emits.
// PRIVACY: the browser's speech recognition sends the voice to the browser maker's speech service, so a consent step comes first
// (micConsent.js). Only counts are saved, on this device (readAloudStore.js). Nothing is sent by Sound Along itself.
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { createReadAlong, cursorIndex, feed, restartFrom, summarize } from "../readAloud.js";
import { calloutText, marksFor, sentenceAround } from "../readAloudMarks.js";
import { createRecognizer } from "../speechRecognizer.js";
import { giveMicConsent, hasMicConsent } from "../micConsent.js";
import { addResult, clearResults, loadResults } from "../readAloudStore.js";
import { langAttr } from "../language.js";
import { wordSlice } from "../timing.js";

const props = defineProps({
  words: { type: Array, required: true },
  language: { type: String, default: "en" },
  passageId: { type: String, required: true },
});
const emit = defineEmits(["marks", "cursor", "hear", "listen", "close"]);

const phase = ref(hasMicConsent() ? "ready" : "consent"); // consent | ready | listening | paused | halted | done
const follower = ref(createReadAlong(props.words, { language: props.language }));
const callout = ref(null);
const starting = ref(false);
const errorText = ref("");
const announcement = ref("");
const savedBefore = ref(loadResults(props.passageId));
const keepsChoice = ref(true);
const calloutButton = ref(null);
let recognizer = null;
let saved = false;

const summary = computed(() => summarize(follower.value));
const message = computed(() => calloutText(callout.value, props.words));
const flagged = computed(() => new Set(callout.value ? (callout.value.indexes ?? [callout.value.index]) : []));
const sentence = computed(() => (callout.value ? sentenceAround(props.words, callout.value.index) : { start: 0, words: [] }));
const canHear = computed(() => callout.value !== null && wordSlice(props.words, callout.value.index) !== null);
const nextWord = computed(() => props.words[cursorIndex(follower.value)]?.text ?? "");
const counts = computed(() => `${summary.value.read} of ${summary.value.total} words read`);

watch([follower, callout], () => emit("marks", marksFor(follower.value, callout.value)), { immediate: true });

const say = (text) => {
  announcement.value = text;
};

function handle(events) {
  if (events.some((e) => e.type === "advance")) emit("cursor", cursorIndex(follower.value) ?? props.words.length - 1);
  const stopEvent = events.find((e) => e.type === "skipped" || e.type === "differs");
  if (stopEvent) {
    callout.value = stopEvent;
    phase.value = "halted";
    recognizer?.stop();
    say(calloutText(stopEvent, props.words));
    nextTick(() => calloutButton.value?.focus());
  } else if (events.some((e) => e.type === "done")) {
    phase.value = "done";
    recognizer?.stop();
    persist();
    say(`Well done. You read ${summary.value.read} of ${summary.value.total} words.`);
  }
}

function onResult(result) {
  if (phase.value !== "listening") return;
  const out = feed(follower.value, result);
  follower.value = out.state;
  handle(out.events);
}

function onStatus(status) {
  starting.value = status === "starting" || status === "restarting";
  if (status === "listening" && phase.value === "listening") say(`Listening. Read from “${nextWord.value}”.`);
}

function onError(info) {
  errorText.value = info.message;
  if (phase.value === "listening") phase.value = "paused";
  say(info.message);
}

function begin() {
  errorText.value = "";
  recognizer ??= createRecognizer({ language: props.language, onResult, onStatus, onError });
  emit("listen"); // the passage audio pauses, or the microphone would hear it
  phase.value = "listening";
  starting.value = true;
  recognizer.start();
}

function persist() {
  if (saved || summary.value.read === 0) return;
  saved = true;
  savedBefore.value = addResult(props.passageId, summary.value, Date.now());
}

function agree() {
  keepsChoice.value = giveMicConsent();
  phase.value = "ready";
}
function pause() {
  recognizer?.stop();
  phase.value = "paused";
  say("Stopped listening.");
}
function carryOn() {
  follower.value = restartFrom(follower.value, cursorIndex(follower.value) ?? 0, { retry: false });
  begin();
}
function readFromHere() {
  follower.value = restartFrom(follower.value, sentence.value.start);
  callout.value = null;
  begin();
}
function startOver() {
  follower.value = createReadAlong(props.words, { language: props.language });
  callout.value = null;
  saved = false;
  emit("cursor", 0);
  begin();
}
function forgetResults() {
  clearResults(props.passageId);
  savedBefore.value = [];
  say("Your reading results were cleared from this device.");
}
function close() {
  recognizer?.stop();
  persist();
  emit("close");
}

onBeforeUnmount(() => {
  recognizer?.stop();
  persist();
  emit("marks", {});
});
</script>

<template>
  <section class="card ra" aria-labelledby="ra-h" @keydown.esc.stop="close">
    <div class="ra-head">
      <h3 id="ra-h">Read aloud with the microphone</h3>
      <button type="button" class="btn ghost" @click="close">Close</button>
    </div>
    <p class="sr-only" role="status" aria-live="polite">{{ announcement }}</p>

    <template v-if="phase === 'consent'">
      <p>To follow along, this uses your browser&rsquo;s own speech recognition. While you read, your browser sends your voice to its speech service (for example Google in Chrome, or Apple in Safari) so it can turn it into words.</p>
      <ul class="small">
        <li>Sound Along does not record your voice and does not keep what you say.</li>
        <li>Only counts, such as how many words you read, are saved, and only on this device.</li>
        <li>Everything else in Sound Along stays on this device. This is the one feature that uses an online service.</li>
        <li>If a child is using this device, a parent or teacher should decide whether to turn it on.</li>
      </ul>
      <div class="row">
        <button type="button" class="btn primary" @click="agree">I agree, continue</button>
        <button type="button" class="btn" @click="close">Not now</button>
      </div>
    </template>

    <template v-else>
      <p v-if="!keepsChoice" class="small muted">Your browser is not saving this choice, so you may be asked again next time.</p>

      <template v-if="phase === 'ready'">
        <p>Press <strong>Start reading</strong>, then read the passage aloud at your own pace. A pause is fine. Only words that are clearly different from the text are pointed out.</p>
        <div class="row"><button type="button" class="btn primary" @click="begin"><span aria-hidden="true">&#9679;</span> Start reading</button></div>
      </template>

      <template v-else-if="phase === 'listening'">
        <p class="state"><span aria-hidden="true" class="dot"></span> <strong>{{ starting ? "Starting the microphone" : "Listening" }}</strong> &middot; {{ counts }}</p>
        <p class="small muted">Read the highlighted word next: <strong :lang="langAttr(language)">{{ nextWord }}</strong></p>
        <div class="row"><button type="button" class="btn" @click="pause">Stop listening</button></div>
      </template>

      <template v-else-if="phase === 'halted' && callout">
        <div class="callout" :class="callout.type">
          <p class="msg"><strong>{{ message }}</strong></p>
          <p class="line" :lang="langAttr(language)">
            <template v-for="w in sentence.words" :key="w.i"><mark v-if="flagged.has(w.i)">{{ w.text }}</mark><template v-else>{{ w.text }}</template>{{ " " }}</template>
          </p>
          <div class="row">
            <button ref="calloutButton" type="button" class="btn primary" @click="readFromHere">Read from here</button>
            <button v-if="canHear" type="button" class="btn" @click="emit('hear', callout.index)">Hear it</button>
          </div>
        </div>
      </template>

      <template v-else-if="phase === 'paused'">
        <p v-if="errorText" class="notice warn" role="note">{{ errorText }}</p>
        <p v-else>Stopped. {{ counts }}.</p>
        <div class="row">
          <button type="button" class="btn primary" @click="carryOn">Keep reading</button>
          <button type="button" class="btn" @click="startOver">Start again</button>
        </div>
      </template>

      <template v-else-if="phase === 'done'">
        <p class="notice ok" role="note"><strong>Well done. You reached the end.</strong></p>
        <div class="row">
          <button type="button" class="btn primary" @click="startOver">Read again</button>
          <button type="button" class="btn" @click="close">Close</button>
        </div>
      </template>

      <dl v-if="phase === 'done' || phase === 'paused'" class="summary">
        <div><dt>Words read</dt><dd>{{ summary.read }} of {{ summary.total }}</dd></div>
        <div><dt>Skipped</dt><dd>{{ summary.skipped }}</dd></div>
        <div><dt>Tried again</dt><dd>{{ summary.retried }}</dd></div>
      </dl>

      <p class="small muted">
        Results stay on this device only.
        <template v-if="savedBefore.length"> {{ savedBefore.length }} earlier {{ savedBefore.length === 1 ? "session is" : "sessions are" }} saved here.
          <button type="button" class="btn ghost small" @click="forgetResults">Clear my reading results</button></template>
      </p>
    </template>
  </section>
</template>

<style scoped>
.ra { display: grid; gap: var(--s2); }
.ra-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s2); }
.row { display: flex; flex-wrap: wrap; gap: var(--s1); }
.state { display: flex; align-items: center; gap: 8px; }
.dot { width: 12px; height: 12px; border-radius: 50%; background: var(--danger); flex: none; }
.callout { display: grid; gap: var(--s2); padding: var(--s2); border-radius: var(--r-sm); border: 2px solid var(--text); background: var(--warn-soft); }
.line { font-family: var(--read); font-size: 20px; line-height: 1.7; }
.line mark { background: var(--hl); color: var(--on-hl); padding: 0 4px; border-radius: 4px; text-decoration: underline wavy; text-underline-offset: 5px; font-weight: 700; }
.summary { display: flex; flex-wrap: wrap; gap: var(--s3); margin: 0; }
.summary dt { font-size: 14px; color: var(--muted); }
.summary dd { margin: 0; font-size: 20px; font-weight: 700; }
</style>

<style>
/* Marks on the passage words while reading aloud. Each state has its own shape, so none relies on colour alone. */
.passage .w[data-ra="read"] { box-shadow: inset 0 -2px 0 var(--primary); }
.passage .w[data-ra="next"] { outline: 2px dashed var(--primary); outline-offset: 2px; font-weight: 700; }
.passage .w[data-ra="skipped"] { background: var(--danger-soft); box-shadow: inset 0 -4px 0 var(--danger); }
.passage .w[data-ra="differs"] { background: var(--warn-soft); box-shadow: inset 0 -4px 0 #8a6d00; }
.passage .w[data-ra="skipped"]::before, .passage .w[data-ra="differs"]::before { font-size: 0.6em; font-weight: 700; vertical-align: super; margin-right: 2px; }
.passage .w[data-ra="skipped"]::before { content: "!"; }
.passage .w[data-ra="differs"]::before { content: "?"; }
</style>
