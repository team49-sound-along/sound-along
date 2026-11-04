<script setup>
// "Help me say it": opens under the read-aloud callout for a skipped or differently heard word. Shows the word in syllables, plays the
// narration of that word slowly, guides one short "say it with me" try, and adds the word to My words. All logic is in syllables.js,
// slowPlay.js, sayItRetry.js and practice.js; this file wires them to the screen.
// PRIVACY: the short try listens through the browser's speech recognition, like the main reading (it sends the voice to the browser maker's
// speech service while it listens). Nothing is recorded or kept: only the star on the word is saved, on this device.
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { syllablesFor, displayWord } from "../syllables.js";
import { slowWindow } from "../slowPlay.js";
import { createRecognizer, recognitionSupported } from "../speechRecognizer.js";
import { finished, initial, judge, step } from "../sayItRetry.js";
import { loadState, saveState, toggleStar } from "../practice.js";
import { wordKey } from "../cards.js";
import { langAttr } from "../language.js";

const props = defineProps({
  words: { type: Array, required: true },
  indexes: { type: Array, required: true }, // the flagged word(s); the first is shown first
  language: { type: String, default: "en" },
  passageId: { type: String, required: true },
});
const emit = defineEmits(["slow", "practice"]);

const LISTEN_LIMIT_MS = 8000;
const SLOW_FALLBACK_MS = 6000;

const open = ref(false);
const chosen = ref(props.indexes[0]);
const parts = ref([]);
const loadFailed = ref(false);
const machine = ref(initial());
const status = ref("");
const myWords = ref(loadState(props.passageId));
const toggleButton = ref(null);
const heading = ref(null);
let recognizer = null;
let listenTimer = null;
let slowTimer = null;

const word = computed(() => displayWord(props.words[chosen.value]?.text));
const key = computed(() => wordKey(props.words[chosen.value]?.text));
const canSlow = computed(() => slowWindow(props.words, chosen.value) !== null);
const canSpeak = recognitionSupported();
const starred = computed(() => Boolean(key.value && myWords.value.words[key.value]));
const choices = computed(() => [...new Set(props.indexes)].filter((i) => displayWord(props.words[i]?.text)));
const oneBeat = computed(() => parts.value.length === 1);
const phase = computed(() => machine.value.phase);
const busy = computed(() => phase.value === "slow" || phase.value === "listening");
const spoken = computed(() => (parts.value.length > 1 ? `${word.value}: ${parts.value.join(", ")}` : word.value));

const COPY = {
  slow: "Listen to the word, slowly.",
  listening: () => `Your turn. Say “${word.value}”.`,
  success: "That’s it. Nicely said! Press Read from here when you are ready.",
  retry: "Almost there. Listen once more, then try again.",
  moveOn: "That one is tricky, and that is fine. Listen again if you like, or press Read from here to keep going.",
  unavailable: (m) => m || "The microphone is not available right now. You can still listen to the word and keep reading.",
};
const message = computed(() => {
  const copy = COPY[phase.value];
  return typeof copy === "function" ? copy(machine.value.message) : (copy ?? "");
});
watch(message, (text) => {
  if (text) status.value = text;
});

async function loadParts() {
  const target = chosen.value;
  loadFailed.value = false;
  try {
    const result = await syllablesFor(props.words[target]?.text, props.language);
    if (target === chosen.value) parts.value = result;
  } catch {
    if (target === chosen.value) {
      parts.value = word.value ? [word.value] : [];
      loadFailed.value = true;
    }
  }
}

function clearTimers() {
  clearTimeout(listenTimer);
  clearTimeout(slowTimer);
  listenTimer = slowTimer = null;
}
function stopListening() {
  recognizer?.stop();
  recognizer = null;
}
function dispatch(event) {
  machine.value = step(machine.value, event);
}

function playSlowly(done) {
  clearTimeout(slowTimer);
  let ended = false;
  const finish = (ok) => {
    if (ended) return;
    ended = true;
    clearTimeout(slowTimer);
    done(ok);
  };
  slowTimer = setTimeout(() => finish(false), SLOW_FALLBACK_MS);
  emit("slow", { index: chosen.value, done: finish });
}

function hearSlowly() {
  stopListening();
  clearTimers();
  dispatch({ type: "stop" });
  status.value = COPY.slow;
  playSlowly(() => {
    status.value = "";
  });
}

function begin(type) {
  clearTimers();
  stopListening();
  dispatch({ type, canSlow: canSlow.value });
}
const sayItWithMe = () => begin("start");
const tryAgain = () => begin("tryAgain");
function notNow() {
  clearTimers();
  stopListening();
  dispatch({ type: "stop" });
  status.value = "";
}

watch(phase, (now) => {
  if (now === "slow") playSlowly((ok) => dispatch({ type: "slowEnded", ok }));
  if (now === "listening") startListening();
  if (finished(machine.value) || now === "retry" || now === "idle") {
    clearTimers();
    stopListening();
  }
});

function startListening() {
  const target = chosen.value;
  recognizer = createRecognizer({
    language: props.language,
    onResult: ({ transcript, isFinal }) => {
      if (phase.value !== "listening" || target !== chosen.value) return;
      const verdict = judge(transcript, props.words[target]?.text, props.language, isFinal);
      if (verdict === "match") dispatch({ type: "heard" });
      else if (verdict === "miss") dispatch({ type: "missed" });
    },
    onError: (info) => dispatch({ type: "failed", message: info.message }),
  });
  recognizer.start();
  listenTimer = setTimeout(() => dispatch({ type: "missed" }), LISTEN_LIMIT_MS);
}

function toggleWord() {
  if (!key.value) return;
  myWords.value = toggleStar(myWords.value, key.value, Date.now());
  saveState(props.passageId, myWords.value);
  status.value = starred.value ? `“${word.value}” was added to My words.` : `“${word.value}” was removed from My words.`;
  emit("practice");
}

async function toggleOpen() {
  open.value = !open.value;
  if (open.value) {
    await loadParts();
    await nextTick();
    heading.value?.focus();
  } else {
    notNow();
    await nextTick();
    toggleButton.value?.focus();
  }
}

function choose(index) {
  if (index === chosen.value) return;
  notNow();
  chosen.value = index;
  parts.value = [];
  loadParts();
}

onBeforeUnmount(() => {
  clearTimers();
  stopListening();
});
</script>

<template>
  <div v-if="word" class="help">
    <button ref="toggleButton" type="button" class="btn" :aria-expanded="open" aria-controls="pron-help" @click="toggleOpen">Help me say it</button>

    <section v-if="open" id="pron-help" class="panel" aria-labelledby="pron-h" @keydown.esc.stop="toggleOpen">
      <h4 id="pron-h" ref="heading" tabindex="-1">How to say <span :lang="langAttr(language)">&ldquo;{{ word }}&rdquo;</span></h4>

      <div v-if="choices.length > 1" class="row" role="group" aria-label="Skipped words">
        <button v-for="i in choices" :key="i" type="button" class="btn small" :aria-pressed="i === chosen" :lang="langAttr(language)" @click="choose(i)">{{ displayWord(words[i].text) }}</button>
      </div>

      <p class="syllables" :lang="langAttr(language)" :aria-label="`Syllables: ${spoken}`" role="group">
        <template v-for="(p, n) in parts" :key="n"><span v-if="n > 0" class="sep" aria-hidden="true">&middot;</span><span class="syl" aria-hidden="true">{{ p }}</span></template>
        <span v-if="!parts.length" class="syl" aria-hidden="true">{{ word }}</span>
      </p>
      <p v-if="oneBeat" class="small muted">This word has one beat. Say it in one go.</p>
      <p v-if="loadFailed" class="small muted" role="note">The word could not be split into syllables here, but you can still listen and try it.</p>

      <div class="row">
        <button v-if="canSlow" type="button" class="btn" :disabled="busy" @click="hearSlowly">Hear it slowly</button>
        <button v-if="canSpeak" type="button" class="btn primary" :disabled="busy" @click="sayItWithMe">Say it with me</button>
        <button type="button" class="btn" :aria-pressed="starred" @click="toggleWord">{{ starred ? "&#9733; In My words" : "&#9734; Add to My words" }}</button>
      </div>

      <div v-if="phase === 'retry'" class="row">
        <button type="button" class="btn primary" @click="tryAgain">Try once more</button>
        <button type="button" class="btn" @click="notNow">Not now</button>
      </div>
      <div v-else-if="busy" class="row"><button type="button" class="btn" @click="notNow">Not now</button></div>

      <p class="msg" :class="{ good: phase === 'success', live: busy }">
        <span v-if="phase === 'success'" aria-hidden="true" class="tick">&#10003;</span>
        <span v-if="phase === 'listening'" aria-hidden="true" class="dot"></span>
        {{ message }}
      </p>
      <p class="sr-only" role="status" aria-live="polite">{{ status }}</p>
    </section>
  </div>
</template>

<style scoped>
.help { display: grid; gap: var(--s1); }
.panel { display: grid; gap: var(--s2); padding: var(--s2); border-radius: var(--r-sm); border: 2px solid var(--primary); background: var(--surface); }
.panel h4 { margin: 0; font-size: 18px; }
.panel h4:focus-visible { outline: 3px solid var(--focus); outline-offset: 3px; }
.row { display: flex; flex-wrap: wrap; gap: var(--s1); }
.syllables { margin: 0; display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px; font-family: var(--read); font-size: clamp(32px, 9vw, 48px); font-weight: 700; line-height: 1.3; color: var(--text); }
.syl { padding: 0 6px; border-radius: 8px; background: var(--primary-soft); }
.sep { color: var(--muted); font-weight: 400; }
.msg { margin: 0; min-height: 1.5em; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.msg.good { color: var(--ok); }
.tick { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 50%; background: var(--ok-soft); border: 2px solid var(--ok); font-size: 14px; }
.dot { width: 12px; height: 12px; border-radius: 50%; background: var(--danger); flex: none; }
@media (prefers-reduced-motion: no-preference) {
  .tick { animation: pop 0.4s ease-out; }
  .dot { animation: beat 1.2s ease-in-out infinite; }
}
@keyframes pop { from { transform: scale(0.6); } to { transform: scale(1); } }
@keyframes beat { 50% { opacity: 0.4; } }
</style>
