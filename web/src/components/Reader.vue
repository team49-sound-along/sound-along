<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import Icon from "./Icon.vue";
import AudioBar from "./AudioBar.vue";
import WordHelp from "./WordHelp.vue";
import { api, audioUrl } from "../api.js";
import { findActiveIndex, seekSeconds, wordSlice } from "../timing.js";
import { route } from "../router.js";
import { isHuman, resumeIndex, voiceLabel } from "../voices.js";

const props = defineProps({
  passageId: { type: String, required: true },
  timing: { type: Object, required: true },
  soundAlong: { type: Boolean, default: true },
  classId: { type: String, default: undefined },
});

const audio = ref(null);
const playNote = ref("");
const activeIndex = ref(-1);
const focusIndex = ref(0);
const playing = ref(false);
const currentMs = ref(0);
const speed = ref(1);
const wordHelp = ref(true);
const vocabNote = ref(null);
const selectedIndex = ref(-1);
let frame = 0;
let stopAtSec = null; // set while "Hear this word" is playing a single word

const words = computed(() => props.timing.words ?? []);
const paragraphs = computed(() =>
  words.value.reduce((groups, w) => {
    const next = groups.slice();
    next[w.paragraph] = [...(next[w.paragraph] ?? []), w];
    return next;
  }, []).filter(Boolean),
);
const selectedWord = computed(() => words.value[selectedIndex.value] ?? null);
const canHear = computed(() => selectedWord.value !== null && wordSlice(words.value, selectedIndex.value) !== null);
const progress = computed(() => (words.value.length ? Math.round(((activeIndex.value + 1) / words.value.length) * 100) : 0));

onBeforeUnmount(() => cancelAnimationFrame(frame));

// Switching voice keeps the reader's place: the other variant opens at the same word (and keeps playing).
const hasPair = computed(() => Boolean(props.timing.pairId));
function switchVoice() {
  const at = Math.max(activeIndex.value, 0);
  const resume = playing.value ? "&play=1" : "";
  location.hash = `#/read/${encodeURIComponent(props.timing.pairId)}?at=${at}${resume}`;
}
onMounted(() => {
  const at = resumeIndex(route.value.query, words.value.length);
  const el = audio.value;
  if (at === null || !el) return;
  const start = () => {
    el.currentTime = seekSeconds(words.value, at);
    activeIndex.value = at;
    focusIndex.value = at;
    revealActive(at);
    if (route.value.query.play === "1") startAudio(el);
  };
  if (el.readyState >= 1) start();
  else el.addEventListener("loadedmetadata", start, { once: true });
});

const track = (type) => api.event({ passageId: props.passageId, type, ...(props.classId ? { classId: props.classId } : {}) });
const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function vocabFor(word) {
  const entry = word?.vocabId ? props.timing.vocab?.[word.vocabId] : null;
  return entry
    ? { word: entry.word, definition: entry.definition, partOfSpeech: entry.partOfSpeech, examples: entry.examples ?? [], spanish: entry.spanish ?? [] }
    : null;
}

function revealActive(index) {
  const el = document.getElementById(`w-${index}`);
  if (!el) return;
  const rect = el.getBoundingClientRect();
  if (rect.top < 190 || rect.bottom > window.innerHeight - 140) {
    el.scrollIntoView({ block: "center", behavior: reduceMotion() ? "auto" : "smooth" });
  }
}

function tick() {
  const el = audio.value;
  if (!el) return;
  if (stopAtSec !== null && el.currentTime >= stopAtSec) {
    stopAtSec = null;
    el.pause(); // onPause runs tick() again to settle the highlight
    return;
  }
  currentMs.value = el.currentTime * 1000;
  const index = findActiveIndex(words.value, currentMs.value);
  if (index !== activeIndex.value) {
    activeIndex.value = index;
    if (index >= 0) {
      const note = vocabFor(words.value[index]);
      if (note) vocabNote.value = note;
      revealActive(index);
    }
  }
  if (playing.value) frame = requestAnimationFrame(tick);
}

const BLOCKED = "Your browser paused the audio. Press Play to start.";
function startAudio(el) {
  playNote.value = "";
  el.play().catch(() => (playNote.value = BLOCKED));
}

function onPlay() {
  playing.value = true;
  playNote.value = "";
  track("play");
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(tick);
}
function onPause() {
  playing.value = false;
  tick();
}
function onEnded() {
  onPause();
  track("complete");
}

function toggle() {
  const el = audio.value;
  if (!el) return;
  stopAtSec = null;
  if (el.paused) startAudio(el);
  else el.pause();
}

function playFrom(index) {
  const el = audio.value;
  if (!el || !props.soundAlong) return;
  stopAtSec = null;
  el.currentTime = seekSeconds(words.value, index);
  focusIndex.value = index;
  selectedIndex.value = index;
  activeIndex.value = index;
  const note = vocabFor(words.value[index]);
  if (note) vocabNote.value = note;
  track("word_tap");
  startAudio(el);
}

// Plays only the selected word. The existing requestAnimationFrame loop (tick) stops it, so it works at any speed.
function hearWord() {
  const el = audio.value;
  const slice = wordSlice(words.value, selectedIndex.value);
  if (!el || !slice) return;
  stopAtSec = slice.endSec;
  el.currentTime = slice.startSec;
  startAudio(el);
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(tick);
}

function seekTo(ms) {
  stopAtSec = null;
  audio.value.currentTime = ms / 1000;
  tick();
}

function changeSpeed(value) {
  speed.value = value;
  audio.value.playbackRate = value;
  audio.value.preservesPitch = true;
}

async function moveFocus(next) {
  const clamped = Math.max(0, Math.min(words.value.length - 1, next));
  focusIndex.value = clamped;
  await nextTick();
  document.getElementById(`w-${clamped}`)?.focus();
}

function hearFocused() {
  selectedIndex.value = focusIndex.value;
  hearWord();
}

function onKey(event) {
  if (!props.soundAlong) return;
  const handlers = {
    ArrowRight: () => moveFocus(focusIndex.value + 1),
    ArrowLeft: () => moveFocus(focusIndex.value - 1),
    Home: () => moveFocus(0),
    End: () => moveFocus(words.value.length - 1),
    Enter: () => playFrom(focusIndex.value),
    " ": () => playFrom(focusIndex.value),
    h: hearFocused,
    H: hearFocused,
  };
  const handler = handlers[event.key];
  if (handler) {
    event.preventDefault();
    handler();
  }
}
</script>

<template>
  <article class="reader" aria-labelledby="reader-h">
    <header class="head">
      <p class="eyebrow">Now reading &middot; {{ voiceLabel(timing.engine) }}</p>
      <h2 id="reader-h">{{ timing.title }}</h2>
      <div v-if="hasPair && soundAlong" class="voice" role="group" aria-label="Narration voice">
        <button type="button" class="btn" :aria-pressed="isHuman(timing)" :disabled="isHuman(timing)" @click="switchVoice">Human narrator</button>
        <button type="button" class="btn" :aria-pressed="!isHuman(timing)" :disabled="!isHuman(timing)" @click="switchVoice">AI voice</button>
      </div>
    </header>

    <template v-if="soundAlong">
      <audio ref="audio" :src="audioUrl(passageId)" preload="auto" @play="onPlay" @pause="onPause" @ended="onEnded" @seeked="tick"></audio>
      <div class="sticky">
        <AudioBar
          :playing="playing" :current-ms="currentMs" :duration-ms="timing.duration_ms" :speed="speed"
          v-model:word-help="wordHelp" @toggle="toggle" @seek="seekTo" @speed="changeSpeed"
        />
        <div class="progress" role="progressbar" aria-label="Reading progress" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="progress">
          <span :style="{ width: progress + '%' }"></span>
        </div>
      </div>
      <p v-if="playNote" role="status" class="notice warn">{{ playNote }}</p>
    </template>
    <div v-else class="notice warn" role="note">
      <Icon name="alert" />
      <p><strong>Audio is off for this assignment.</strong> Your teacher has turned Sound Along off, so you can read the text on your own.</p>
    </div>

    <p v-if="soundAlong" id="reader-help" class="hint small muted">
      <Icon name="keyboard" :size="18" />
      <span>Tap or click any word to hear it from there. Keyboard: arrow keys move between words, Enter or Space plays, H plays just that word.</span>
    </p>
    <div class="passage" role="group" aria-label="Passage text" :aria-describedby="soundAlong ? 'reader-help' : undefined" @keydown="onKey">
      <p v-for="(para, n) in paragraphs" :key="n">
        <template v-for="w in para" :key="w.i">
          <span
            :id="`w-${w.i}`" class="w"
            :class="{ active: soundAlong && w.i === activeIndex, vocab: wordHelp && w.vocabId, tappable: soundAlong }"
            :tabindex="soundAlong && w.i === focusIndex ? 0 : -1"
            :role="soundAlong ? 'button' : undefined"
            @click="playFrom(w.i)"
            @focus="selectedIndex = w.i"
          >{{ w.text }}</span>{{ " " }}
        </template>
      </p>
    </div>

    <WordHelp v-if="soundAlong" :note="vocabNote" :show-note="wordHelp" :word="selectedWord?.text ?? ''" :can-hear="canHear" @hear="hearWord" />
  </article>
</template>

<style scoped>
.reader { display: grid; gap: var(--s2); }
.head h2 { font-size: 28px; }
.sticky { position: sticky; top: calc(var(--topbar-h) + 8px); z-index: 20; display: grid; gap: 0; }
.progress { height: 4px; margin: 0 12px; border-radius: 0 0 4px 4px; background: var(--border); overflow: hidden; }
.progress span { display: block; height: 100%; background: var(--primary); transition: width 0.2s; }
.hint { display: flex; align-items: center; gap: 8px; }
.passage { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: var(--s4) var(--s4); font-family: var(--read); font-size: 24px; line-height: 2; display: grid; gap: var(--s2); }
.w { padding: 2px 3px; margin: 0 -3px; border-radius: 6px; box-decoration-break: clone; -webkit-box-decoration-break: clone; transition: background-color 0.08s; }
.w.tappable { cursor: pointer; }
.w.tappable:hover { background: var(--primary-soft); }
.w.vocab { text-decoration: underline dotted; text-decoration-thickness: 2px; text-underline-offset: 6px; }
.w.active, .w.active:hover { background: var(--hl); color: var(--on-hl); box-shadow: 0 0 0 2px var(--hl); }
.w:focus-visible { outline: 3px solid var(--focus); outline-offset: 1px; }
.voice { display: inline-flex; gap: 8px; margin-top: var(--s1); }
.voice .btn[aria-pressed="true"] { background: var(--primary); border-color: var(--primary); color: var(--on-primary); opacity: 1; }
.notice { align-items: center; }
@media (max-width: 640px) {
  .passage { padding: var(--s3) var(--s2); font-size: 22px; }
  .head h2 { font-size: 24px; }
}
</style>
