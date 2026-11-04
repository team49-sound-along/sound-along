<script setup>
// "Read aloud with the microphone": the learner reads the passage, the panel follows word by word and stops with a plain explanation when a
// word is skipped or clearly heard as a different word. Logic lives in readAloud.js (follower) and speechRecognizer.js (browser speech
// recognition); this file only wires them to the screen. The reader draws the marks this panel emits.
// PRIVACY: the browser's speech recognition sends the voice to the browser maker's speech service; the panel says so in one short line and
// the browser asks for the microphone itself. The school (teacher switches) decides whether the feature is offered and whether anonymous
// word counts are shared. Sound Along never records audio and never keeps what was said. Counts are saved on this device (readAloudStore.js);
// at the end of a session ONE anonymous result is sent, only when the class allows it (readAloudShare.js).
import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from "vue";
import { createReadAlong, cursorIndex, feed, restartFrom, summarize } from "../readAloud.js";
import { calloutText, marksFor, marksSignature, nudgeText, sentenceAround } from "../readAloudMarks.js";
import { loadMode, saveMode } from "../readAloudMode.js";
import { createRecognizer } from "../speechRecognizer.js";
import { api } from "../api.js";
import { buildSharePayload } from "../readAloudShare.js";
import { readerCode, readerLabel, startNewReaderCode } from "../readerCode.js";
import { addResult, clearResults, loadResults } from "../readAloudStore.js";
import { langAttr } from "../language.js";
import { wordSlice } from "../timing.js";
import PronunciationHelp from "./PronunciationHelp.vue";
import PracticeWords from "./PracticeWords.vue";

const props = defineProps({
  words: { type: Array, required: true },
  language: { type: String, default: "en" },
  passageId: { type: String, required: true },
  sharePassageId: { type: String, default: undefined }, // the passage whose own word positions these are (not the shared practice id)
  classId: { type: String, default: undefined },
  share: { type: Boolean, default: false }, // the class shares anonymous word counts and this is a student
  readers: { type: Boolean, default: false }, // the class shows progress by anonymous reader code
});
const emit = defineEmits(["marks", "cursor", "hear", "listen", "close", "slow", "practice"]);

const phase = ref("ready"); // ready | listening | paused | halted | done
const mode = ref(loadMode());
const fresh = () => createReadAlong(props.words, { language: props.language, mode: mode.value });
const follower = shallowRef(fresh()); // replaced, never mutated: no deep proxy over a long passage
const callout = ref(null);
const starting = ref(false);
const errorText = ref("");
const announcement = ref("");
const savedBefore = ref(loadResults(props.passageId));
const code = ref(props.share && props.readers ? readerCode() : null);
const calloutButton = ref(null);
const nudge = ref(null); // the gentle reminder shown while the learner keeps reading
let nudgeTimer = null;
const NUDGE_MS = 9000;
let recognizer = null;
let saved = false;
let began = false;
let shared = false;

const summary = computed(() => summarize(follower.value));
const message = computed(() => calloutText(callout.value, props.words));
const flagged = computed(() => new Set(callout.value ? (callout.value.indexes ?? [callout.value.index]) : []));
const sentence = computed(() => (callout.value ? sentenceAround(props.words, callout.value.index) : { start: 0, words: [] }));
const canHear = computed(() => callout.value !== null && wordSlice(props.words, callout.value.index) !== null);
const nextWord = computed(() => props.words[cursorIndex(follower.value)]?.text ?? "");
const counts = computed(() => `${summary.value.read} of ${summary.value.total} words read`);

let lastMarks = null;
watch([follower, callout], () => {
  const signature = marksSignature(follower.value, callout.value);
  if (signature === lastMarks) return; // interim results that change nothing visible
  lastMarks = signature;
  emit("marks", marksFor(follower.value, callout.value));
}, { immediate: true });

const say = (text) => {
  announcement.value = text;
};

function clearNudge() {
  clearTimeout(nudgeTimer);
  nudgeTimer = null;
  nudge.value = null;
}
function showNudge(miss) {
  nudge.value = { ...miss, text: nudgeText(miss, props.words) };
  say(nudge.value.text + " You can go back, or keep reading.");
  clearTimeout(nudgeTimer);
  nudgeTimer = setTimeout(clearNudge, NUDGE_MS);
}
/** "Go back": restart at the start of the sentence with the missed word. The microphone keeps listening, so reading just continues from there. */
function goBack() {
  if (!nudge.value) return;
  const at = sentenceAround(props.words, nudge.value.index).start;
  clearNudge();
  follower.value = restartFrom(follower.value, at);
  emit("cursor", at);
  say("Read again from the start of that sentence.");
}
function chooseMode(next) {
  mode.value = next;
  saveMode(next);
  // Before reading starts a fresh follower is made; while reading, only the mode changes, so the place and what was read are kept.
  follower.value = phase.value === "ready" ? fresh() : { ...follower.value, mode: next };
  if (next === "stop") clearNudge();
}

function handle(events) {
  const missedNow = events.filter((e) => e.type === "missed");
  if (missedNow.length) showNudge(missedNow.at(-1));
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
    shareResult();
    say(`Well done. You read ${summary.value.read} of ${summary.value.total} words.`);
  }
}

function onResult(result) {
  // "paused" is accepted too: Stop flushes the last spoken words as a final result a moment after the phase changes.
  if (phase.value !== "listening" && phase.value !== "paused") return;
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
  began = true;
  starting.value = true;
  recognizer.start();
}

function persist() {
  if (saved || summary.value.read === 0) return;
  saved = true;
  savedBefore.value = addResult(props.passageId, summary.value, Date.now());
}

/** One anonymous result per session, only when the class shares and the session really started. */
function shareResult() {
  if (shared || !began || !props.share) return;
  shared = true;
  const payload = buildSharePayload({ passageId: props.sharePassageId ?? props.passageId, classId: props.classId, language: props.language, state: follower.value, readerCode: props.readers ? code.value : null });
  if (payload) api.shareReadAloud(payload);
}
function newCode() {
  code.value = startNewReaderCode();
  say("Started a new reader code.");
}
function pause() {
  recognizer?.stop();
  phase.value = "paused";
  say("Stopped listening.");
}
/** The passage narration started while the microphone was on: stop listening so the voice is not mistaken for the learner. */
function pauseForNarration() {
  if (phase.value !== "listening") return;
  recognizer?.stop();
  phase.value = "paused";
  say("Paused while the passage plays. Press Keep reading when you are ready.");
}
defineExpose({ pauseForNarration });
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
  persist();
  shareResult(); // the session being left is shared before a fresh one starts
  follower.value = fresh();
  callout.value = null;
  clearNudge();
  saved = false;
  shared = false;
  began = false;
  emit("cursor", 0);
  begin();
}
function forgetResults() {
  clearResults(props.passageId);
  savedBefore.value = [];
  say("Your reading results were cleared from this device.");
}
function close() {
  clearNudge();
  recognizer?.stop();
  persist();
  shareResult();
  emit("close");
}

onBeforeUnmount(() => {
  clearNudge();
  recognizer?.stop();
  persist();
  shareResult();
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

    <div v-if="nudge && phase === 'listening'" class="nudge" role="group" aria-label="Reminder" data-testid="ra-nudge">
      <span class="nudge-text" :lang="langAttr(language)">{{ nudge.text }}</span>
      <button type="button" class="btn small" @click="goBack">Go back</button>
      <button type="button" class="btn ghost small" aria-label="Dismiss reminder" @click="clearNudge">&times;</button>
    </div>

    <div class="ra-body">
    <fieldset class="mode">
          <legend class="small">When I miss a word</legend>
          <label><input type="radio" name="ra-mode" value="keepGoing" :checked="mode === 'keepGoing'" @change="chooseMode('keepGoing')" /> Keep going and remind me</label>
          <label><input type="radio" name="ra-mode" value="stop" :checked="mode === 'stop'" @change="chooseMode('stop')" /> Stop and guide me back</label>
        </fieldset>

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
          <PronunciationHelp :key="callout.index" :words="words" :indexes="callout.indexes ?? [callout.index]" :language="language" :passage-id="passageId" @slow="emit('slow', $event)" @practice="emit('practice')" />
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

      <PracticeWords v-if="phase === 'done' || phase === 'paused'" :follower="follower" :words="words" :passage-id="passageId" :language="language" @practice="emit('practice')" />

      <p v-if="phase !== 'listening'" class="small muted">Your browser&rsquo;s speech service listens while this is on.</p>
      <p class="small muted" data-testid="ra-privacy">
        <template v-if="share">Only anonymous word counts are shared with your teacher, never your voice or name. </template>
        <template v-else>Nothing about your reading is shared. </template>
        Your own results stay on this device.
        <template v-if="savedBefore.length"> {{ savedBefore.length }} earlier {{ savedBefore.length === 1 ? "session is" : "sessions are" }} saved here.
          <button type="button" class="btn ghost small" @click="forgetResults">Clear my reading results</button></template>
      </p>
      <p v-if="share && readers && code" class="small muted" data-testid="ra-reader">
        You are <strong>{{ readerLabel(code) }}</strong>. This code is not your name. <button type="button" class="btn ghost small" @click="newCode">Start a new reader code</button>
      </p>
    </div>
  </section>
</template>

<style scoped>
.mode { border: 0; padding: 0; margin: 0; display: grid; gap: 6px; min-width: 0; } /* a fieldset is as wide as its content by default, which pushed the page wider than a phone */
.mode legend { font-weight: 700; margin-bottom: 2px; }
.mode label { display: flex; align-items: center; gap: 8px; min-height: 32px; }
.nudge { position: fixed; z-index: 40; left: 12px; right: 12px; margin: 0 auto; width: fit-content; bottom: calc(var(--dock-h, 72px) + 14px); display: flex; align-items: center; gap: 10px; max-width: min(calc(100vw - 24px), 560px); padding: 10px 14px; border-radius: 14px; background: var(--surface); border: 1px solid var(--border); box-shadow: 0 6px 24px rgba(0, 0, 0, 0.16); }
.nudge-text { font-size: 16px; }
.ra { display: grid; gap: var(--s2); }
.ra-body { display: grid; gap: var(--s2); }
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
.passage .w[data-ra="read"] { background: var(--hl); color: var(--on-hl); box-shadow: inset 0 -2px 0 #8a6d00; }
.passage .w[data-ra="next"] { outline: 2px dashed #8a6d00; outline-offset: 2px; font-weight: 700; }
.passage .w[data-ra="skipped"] { background: var(--danger-soft); box-shadow: inset 0 -4px 0 var(--danger); }
.passage .w[data-ra="differs"] { background: var(--warn-soft); box-shadow: inset 0 -4px 0 #8a6d00; }
.passage .w[data-ra="skipped"]::before, .passage .w[data-ra="differs"]::before { font-size: 0.6em; font-weight: 700; vertical-align: super; margin-right: 2px; }
.passage .w[data-ra="skipped"]::before { content: "!"; }
.passage .w[data-ra="differs"]::before { content: "?"; }
</style>
