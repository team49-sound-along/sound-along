<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import Icon from "./Icon.vue";
import AudioBar from "./AudioBar.vue";
import WordHelp from "./WordHelp.vue";
import QuizButton from "./QuizButton.vue";
import ReadingSettings from "./ReadingSettings.vue";
import ReadAloudPanel from "./ReadAloudPanel.vue";
import { recognitionSupported } from "../speechRecognizer.js";
import { createSlowPlayer, slowWindow } from "../slowPlay.js";
import { readAloudSettingsFor } from "../readAloudShare.js";
import { api, audioUrl, fetchCards } from "../api.js";
import { findWordCard, placeAt, wordKey } from "../cards.js";
import { loadState, saveState, toggleStar } from "../practice.js";
import { role } from "../session.js";
import { langAttr } from "../language.js";
import { activeSentence, phraseLines, sentenceStart } from "../phrases.js";
import { applyMotionPreference, loadPrefs, prefsToCssVars, savePrefs } from "../readingPrefs.js";
import { followAction } from "../readerFollow.js";
import { findActiveIndex, seekSeconds, wordSlice } from "../timing.js";
import { route } from "../router.js";
import { firstWordOfSentence, isHuman, LANGUAGE_NAMES, languageSwitch, resumeIndex, resumeSentence, targetSentence, voiceLabel } from "../voices.js";

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
const selectedIndex = ref(-1);
const cards = ref(null);
const showSettings = ref(false);
const settingsButton = ref(null);
// Read aloud with the microphone (ReadAloudPanel): the panel follows the learner and sends back a mark for each word.
// The teacher decides per class whether the button is offered and whether anonymous word counts are shared (loaded here; until it has loaded,
// or if it cannot be loaded, the button is hidden and nothing is shared).
const raSettings = ref({ mic: false, share: false, readers: false });
api.readAloudSettings().then((view) => { raSettings.value = readAloudSettingsFor(view, props.classId); }).catch(() => {});
const canReadAloud = computed(() => recognitionSupported() && raSettings.value.mic);
const shareReadAloud = computed(() => raSettings.value.share && role.value === "student"); // a teacher trying it out adds nothing to the counts
const readAloudOn = ref(false);
const readAloudButton = ref(null);
const raMarks = shallowRef({});
const raPanel = ref(null);
function closeReadAloud() {
  readAloudOn.value = false;
  nextTick(() => readAloudButton.value?.focus());
}
function hearAt(index) {
  selectedIndex.value = index;
  hearWord();
}
// "Hear it slowly" from the pronunciation help: the word's own narration slice at a slower speed, pitch kept (slowPlay.js).
const slowPlayer = createSlowPlayer();
function slowAt({ index, done }) {
  stopAtSec = null;
  slowPlayer.play(audio.value, slowWindow(words.value, index), done);
}
const dock = ref(null);
const dockHeight = ref(0);
let dockObserver = null;
let frame = 0;
let stopAtSec = null; // set while "Hear this word" is playing a single word

// Reading preferences live on this device only. Storage can be blocked, so access goes through a guard.
const getStorage = () => {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
};
const prefs = ref(loadPrefs(getStorage()));
watch(prefs, (next) => {
  savePrefs(getStorage(), next);
  applyMotionPreference(document.documentElement, next); // the whole app calms down at once, not only this passage
});
const cssVars = computed(() => prefsToCssVars(prefs.value));

const words = computed(() => props.timing.words ?? []);
const paragraphs = computed(() =>
  words.value.reduce((groups, w) => {
    const next = groups.slice();
    next[w.paragraph] = [...(next[w.paragraph] ?? []), w];
    return next;
  }, []).filter(Boolean),
);
// Each paragraph becomes lines: one line per phrase when phrase breaks are on, otherwise a single flowing line.
const layout = computed(() => paragraphs.value.map((para) => (prefs.value.phraseBreaks ? phraseLines(para) : [para])));
const selectedWord = computed(() => words.value[selectedIndex.value] ?? null);
const canHear = computed(() => selectedWord.value !== null && wordSlice(words.value, selectedIndex.value) !== null);
const card = computed(() => findWordCard(cards.value, props.timing.vocab, selectedWord.value?.text));
// Pictures that sit between paragraphs in the original passage (cards.figures). Only same-origin /data/ pictures are shown.
const figures = computed(() => (cards.value?.figures ?? []).filter((f) => f && typeof f.imageUrl === "string" && f.imageUrl.startsWith("/data/") && Number.isInteger(f.afterParagraph)));
const figuresAt = (n) => figures.value.filter((f) => (n === layout.value.length ? f.afterParagraph >= n : f.afterParagraph === n));
const place = computed(() => placeAt(words.value, selectedIndex.value, cards.value?.places));
const highlightOn = computed(() => props.soundAlong && prefs.value.highlight !== "off");
const bandSentence = computed(() => (highlightOn.value ? activeSentence(words.value, activeIndex.value) : null));

const isBand = (w) => bandSentence.value !== null && w.sentence === bandSentence.value;

onBeforeUnmount(() => {
  window.removeEventListener("scroll", hideJumpWhenVisible);
  cancelAnimationFrame(frame);
  dockObserver?.disconnect();
});

// Switching voice keeps the reader's place: the other variant opens at the same word (and keeps playing).
const hasPair = computed(() => Boolean(props.timing.pairId));
// Practice: "Save word" stars a word for flashcards. Kept in this browser only (see practice.js). The human variant shares the AI passage's progress.
const practiceId = computed(() => (props.timing.engine === "human" && props.timing.pairId ? props.timing.pairId : props.passageId));
const practiceState = ref(loadState(practiceId.value));
const selectedKey = computed(() => wordKey(selectedWord.value?.text));
const isStarred = computed(() => Boolean(selectedKey.value && practiceState.value.words[selectedKey.value]));
function toggleSaved() {
  if (!selectedKey.value) return;  // any word can be saved; a word with no card is practised by its sound
  practiceState.value = toggleStar(practiceState.value, selectedKey.value, Date.now());
  saveState(practiceId.value, practiceState.value);
}
// Words that have a picture or sit inside a place card get a visible cue (a mark, not only a colour).
const pictureKeys = computed(() => new Set(Object.entries(cards.value?.words ?? {}).filter(([, c]) => c?.imageUrl).map(([k]) => k)));
const placeWords = computed(() => new Set(words.value.filter((w) => placeAt(words.value, w.i, cards.value?.places)).map((w) => w.i)));
// Words with a definition card get the same dotted underline as the passage's own vocabulary.
const definedKeys = computed(() => new Set(Object.entries(cards.value?.words ?? {}).filter(([, c]) => c?.definition || c?.translation?.words?.length).map(([k]) => k)));
const hasVisual = (w) => wordHelp.value && (pictureKeys.value.has(wordKey(w.text)) || placeWords.value.has(w.i));
// Language switch: the text's translation (or its source) is a separate passage linked in the timing document. The sentence map keeps the place.
const langSwitch = computed(() => languageSwitch(props.timing));
const currentLang = computed(() => props.timing.language || "en");
function switchLanguage() {
  const sw = langSwitch.value;
  if (!sw) return;
  const at = activeIndex.value >= 0 ? activeIndex.value : focusIndex.value;
  const sentence = targetSentence(sw, words.value[Math.max(0, at)]?.sentence ?? 0);
  const resume = playing.value ? "&play=1" : "";
  location.hash = `#/read/${encodeURIComponent(sw.id)}?s=${sentence}${resume}`;
}
function switchVoice() {
  const at = activeIndex.value >= 0 ? activeIndex.value : focusIndex.value;
  const resume = playing.value ? "&play=1" : "";
  location.hash = `#/read/${encodeURIComponent(props.timing.pairId)}?at=${at}${resume}`;
}
onMounted(() => {
  window.addEventListener("scroll", hideJumpWhenVisible, { passive: true });
  applyMotionPreference(document.documentElement, prefs.value);
  if (dock.value && typeof ResizeObserver !== "undefined") {
    dockObserver = new ResizeObserver(([entry]) => (dockHeight.value = Math.ceil(entry.contentRect.height)));
    dockObserver.observe(dock.value);
  }
  // Cards are an optional JSON document. Without one the reader uses the passage vocabulary (fetchCards never rejects).
  // A text has an AI and a human variant with separate ids; cards are stored once, so try this id and then its pair.
  fetchCards(props.passageId)
    .then((data) => data ?? (props.timing.pairId ? fetchCards(props.timing.pairId) : null))
    .then((data) => (cards.value = data));

  const bySentence = resumeSentence(route.value.query);
  const at = bySentence !== null ? firstWordOfSentence(words.value, bySentence) : resumeIndex(route.value.query, words.value.length);
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
const reduceMotion = () => prefs.value.reduceMotion || window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// With Reduce motion the page never scrolls by itself: when the spoken word is off screen a button offers the jump instead.
const offerJump = ref(false);
function revealActive(index) {
  const el = document.getElementById(`w-${index}`);
  if (!el) return;
  const action = followAction({ reduce: reduceMotion(), rect: el.getBoundingClientRect(), bottomLimit: window.innerHeight - dockHeight.value - 24 });
  if (action === "scroll") el.scrollIntoView({ block: "center", behavior: "smooth" });
  offerJump.value = action === "offer-jump";
}
function jumpToActive() {
  document.getElementById(`w-${activeIndex.value}`)?.scrollIntoView({ block: "center", behavior: "auto" });
  offerJump.value = false;
}
const hideJumpWhenVisible = () => {
  if (!offerJump.value) return;
  const el = document.getElementById(`w-${activeIndex.value}`);
  if (el) offerJump.value = followAction({ reduce: true, rect: el.getBoundingClientRect(), bottomLimit: window.innerHeight - dockHeight.value - 24 }) === "offer-jump";
};

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
    if (index >= 0) revealActive(index);
  }
  if (playing.value) frame = requestAnimationFrame(tick);
}

const BLOCKED = "Your browser paused the audio. Press Play to start.";
const FAILED = "The audio could not be loaded. You can keep reading the text. Check your connection, then press Play to try again.";
function startAudio(el) {
  playNote.value = "";
  el.play().catch((e) => (playNote.value = e?.name === "NotAllowedError" ? BLOCKED : FAILED));
}
function onAudioError() {
  playNote.value = FAILED;
}

function onPlay() {
  playing.value = true;
  playNote.value = "";
  raPanel.value?.pauseForNarration(); // the microphone must not hear the narration
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
  track("word_tap");
  startAudio(el);
}

// Back or forward one sentence. Keeps playing if it was playing, and stays paused if it was paused.
function skip(direction) {
  const el = audio.value;
  const to = sentenceStart(words.value, activeIndex.value, direction);
  if (!el || to === null) return;
  stopAtSec = null;
  el.currentTime = seekSeconds(words.value, to);
  focusIndex.value = to;
  activeIndex.value = to;
  revealActive(to);
  tick();
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
  if (!audio.value) return;
  stopAtSec = null;
  audio.value.currentTime = ms / 1000;
  tick();
}

function changeSpeed(value) {
  speed.value = value;
  if (!audio.value) return;
  audio.value.playbackRate = value;
  audio.value.preservesPitch = true;
}

async function moveFocus(next) {
  const clamped = Math.max(0, Math.min(words.value.length - 1, next));
  focusIndex.value = clamped;
  await nextTick();
  document.getElementById(`w-${clamped}`)?.focus();
}

// Return focus to the button that opened the panel, so keyboard users do not land on the page body.
async function closeSettings() {
  showSettings.value = false;
  await nextTick();
  settingsButton.value?.focus();
}

function hearFocused() {
  selectedIndex.value = focusIndex.value;
  hearWord();
}

function onKey(event) {
  if (!props.soundAlong || event.altKey || event.metaKey || event.ctrlKey) return; // keep browser shortcuts such as Cmd+Left
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
  <article class="reader" aria-labelledby="reader-h" :style="{ '--dock-h': dockHeight + 'px' }">
    <header class="head">
      <p class="eyebrow">{{ words.length }} words<template v-if="role === 'teacher'"> &middot; {{ voiceLabel(timing.engine) }}</template></p>
      <h2 id="reader-h">{{ timing.title }}</h2>
      <div class="tools">
        <div v-if="hasPair && soundAlong && role === 'teacher'" class="voice" role="group" aria-label="Narration voice">
          <button type="button" class="btn" :aria-pressed="isHuman(timing)" :disabled="isHuman(timing)" @click="switchVoice">Human narration</button>
          <button type="button" class="btn" :aria-pressed="!isHuman(timing)" :disabled="!isHuman(timing)" @click="switchVoice">Read-aloud voice</button>
        </div>
        <div v-if="langSwitch" class="voice lang" role="group" aria-label="Language">
          <button type="button" class="btn" :lang="currentLang" :aria-pressed="true" disabled>{{ LANGUAGE_NAMES[currentLang] || currentLang }}</button>
          <button type="button" class="btn" :lang="langSwitch.lang" :aria-pressed="false" @click="switchLanguage">{{ LANGUAGE_NAMES[langSwitch.lang] || langSwitch.lang }}</button>
        </div>
        <a class="btn" :href="`#/practice/${encodeURIComponent(practiceId)}`">Practice words</a>
        <button v-if="canReadAloud" ref="readAloudButton" type="button" class="btn" :aria-expanded="readAloudOn" @click="readAloudOn = !readAloudOn"><Icon name="speak" /> Read aloud with the mic</button>
        <QuizButton :passage-id="passageId" :timing="timing" />
        <button ref="settingsButton" type="button" class="btn" :aria-expanded="showSettings" :aria-controls="showSettings ? 'reading-settings' : undefined" @click="showSettings = !showSettings">
          <Icon name="settings" /> Reading settings
        </button>
      </div>
    </header>

    <p v-if="timing.machineTranslated" class="small muted" role="note">Translated automatically.</p>
    <ReadingSettings v-if="showSettings" :prefs="prefs" @change="prefs = $event" @close="closeSettings" />
    <ReadAloudPanel
      v-if="readAloudOn" ref="raPanel" :words="words" :language="timing.language || 'en'" :passage-id="practiceId" :share-passage-id="passageId"
      :class-id="classId" :share="shareReadAloud" :readers="raSettings.readers"
      @marks="raMarks = $event" @cursor="revealActive" @hear="hearAt" @slow="slowAt" @practice="practiceState = loadState(practiceId)" @listen="audio?.pause()" @close="closeReadAloud"
    />

    <audio v-if="soundAlong" ref="audio" :src="audioUrl(passageId)" preload="auto" @play="onPlay" @pause="onPause" @ended="onEnded" @seeked="tick" @error="onAudioError"></audio>
    <p v-if="soundAlong && playNote" role="status" class="notice warn">{{ playNote }}</p>
    <div v-if="!soundAlong" class="notice warn" role="note">
      <Icon name="alert" />
      <p><strong>Audio is off for this assignment.</strong> Your teacher has turned Sound Along off, so you can read the text on your own.</p>
    </div>

    <div class="stage">
      <div class="body">
        <p v-if="soundAlong" id="reader-help" class="hint small muted">
          <Icon name="keyboard" :size="18" />
          <span>Tap or click any word to hear it from there. Keyboard: arrow keys move between words, Enter or Space plays, H plays just that word.</span>
        </p>
        <div
          class="passage" :class="{ phrased: prefs.phraseBreaks, calm: prefs.reduceMotion }" :style="cssVars"
          :lang="langAttr(timing.language)" role="group" aria-label="Passage text" :aria-describedby="soundAlong ? 'reader-help' : undefined" @keydown="onKey"
        >
          <template v-for="(lines, n) in layout" :key="n">
          <figure v-for="(f, fi) in figuresAt(n)" :key="`f${n}-${fi}`" class="fig">
            <img :src="f.imageUrl" :alt="f.imageAlt || ''" :width="f.imageWidth || undefined" :height="f.imageHeight || undefined" loading="lazy" decoding="async" @error="$event.target.closest('figure').hidden = true" />
            <figcaption v-if="f.caption || f.credit">{{ f.caption }}<span v-if="f.credit" class="credit"> {{ timing.language === "es" ? "Foto" : "Photo" }}: {{ f.credit }}</span></figcaption>
          </figure>
          <p>
            <span v-for="(line, l) in lines" :key="l" class="line">
              <template v-for="(w, k) in line" :key="w.i">
                <span
                  :id="`w-${w.i}`" class="w" :data-ra="raMarks[w.i]"
                  :class="{ active: highlightOn && prefs.highlight === 'words' && w.i === activeIndex, band: isBand(w), vocab: wordHelp && (w.vocabId || definedKeys.has(wordKey(w.text))), tappable: soundAlong, haspic: hasVisual(w) }"
                  :tabindex="soundAlong && w.i === focusIndex ? 0 : -1"
                  :role="soundAlong ? 'button' : undefined"
                  @click="playFrom(w.i)"
                >{{ w.text }}</span><span v-if="k < line.length - 1 && !line[k + 1].join" class="sp" :class="{ band: isBand(w) && line[k + 1].sentence === w.sentence }">{{ " " }}</span>
              </template>
            </span>
          </p>
          </template>
          <figure v-for="(f, fi) in figuresAt(layout.length)" :key="`fe-${fi}`" class="fig">
            <img :src="f.imageUrl" :alt="f.imageAlt || ''" :width="f.imageWidth || undefined" :height="f.imageHeight || undefined" loading="lazy" decoding="async" @error="$event.target.closest('figure').hidden = true" />
            <figcaption v-if="f.caption || f.credit">{{ f.caption }}<span v-if="f.credit" class="credit"> {{ timing.language === "es" ? "Foto" : "Photo" }}: {{ f.credit }}</span></figcaption>
          </figure>
        </div>
      </div>
      <div v-if="soundAlong" class="side" tabindex="0" role="group" aria-label="Word help panel">
        <WordHelp :card="card" :place="place" :show-note="wordHelp" :word="selectedWord?.text ?? ''" :can-hear="canHear" :starred="isStarred" @hear="hearWord" @star="toggleSaved" />
      </div>
    </div>

    <div v-if="soundAlong" ref="dock" class="dock">
      <div v-if="offerJump" class="jump-row"><button type="button" class="btn primary" @click="jumpToActive">Jump to the word being read</button></div>
      <AudioBar
        :playing="playing" :current-ms="currentMs" :duration-ms="timing.duration_ms" :speed="speed"
        v-model:word-help="wordHelp" @toggle="toggle" @seek="seekTo" @speed="changeSpeed" @skip="skip"
      />
    </div>
  </article>
</template>

<style scoped>
.reader { --band: #e2ebe4; display: grid; gap: var(--s3); }
.head h2 { font-size: 40px; letter-spacing: -0.02em; line-height: 1.15; margin-top: 4px; }
.tools { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s1) var(--s2); margin-top: var(--s2); }
.stage { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: var(--s5); align-items: start; }
.side { position: sticky; top: calc(var(--topbar-h) + var(--s2)); }
.body { display: grid; gap: var(--s2); min-width: 0; }
.jump-row { display: flex; justify-content: center; padding: 8px 0; background: var(--surface); }
.dock { position: sticky; bottom: 0; z-index: 20; margin: 0 calc(var(--s2) * -1); }
.dock :deep(.bar) { border-radius: 0; border-width: 1px 0 0; padding: 12px var(--s3); }
.hint { display: flex; align-items: center; gap: 8px; }
.passage {
  font-family: var(--read-font, var(--read)); font-size: var(--read-size, 24px); line-height: var(--read-lh, 2);
  letter-spacing: var(--read-ls, 0); word-spacing: var(--read-ws, 0); display: grid; gap: var(--s3); padding: var(--s1) 0 var(--s3);
}
.passage p { max-width: 32em; }
.fig { margin: var(--s2) 0; max-width: 32em; }
.fig[hidden] { display: none; }
.fig img { display: block; width: auto; max-width: 100%; height: auto; max-height: 360px; border-radius: 12px; background: var(--border); }
.fig figcaption { margin-top: 6px; font-size: 14px; line-height: 1.4; letter-spacing: normal; word-spacing: normal; color: var(--muted); }
.fig .credit { display: block; font-size: 13px; }
.phrased .line { display: block; text-wrap: balance; }
.w { padding: 2px 3px; margin: 0 -3px; border-radius: 6px; box-decoration-break: clone; -webkit-box-decoration-break: clone; transition: background-color 0.08s; }
.calm .w { transition: none; }
.w.band, .sp.band { background: var(--band); }
.w.tappable { cursor: pointer; }
.w.tappable:hover { background: var(--primary-soft); }
.w.haspic::after { content: "\25A3"; font-size: 0.55em; vertical-align: super; margin-left: 1px; opacity: 0.75; }
.w.vocab { text-decoration: underline dotted; text-decoration-thickness: 2px; text-underline-offset: 6px; }
.w.active, .w.active:hover { background: var(--hl); color: var(--on-hl); box-shadow: inset 0 -3px 0 #8a6d00; }
.w:focus-visible { outline: 3px solid var(--focus); outline-offset: 1px; }
.voice { display: inline-flex; gap: 8px; }
.voice .btn[aria-pressed="true"] { background: var(--primary); border-color: var(--primary); color: var(--on-primary); opacity: 1; }
.notice { align-items: center; }
@media (max-width: 960px) {
  .stage { grid-template-columns: minmax(0, 1fr); gap: var(--s3); }
  /* On a phone the word card sticks just above the player, so a tapped word's definition is always in view. */
  .side { position: sticky; top: auto; bottom: var(--dock-h, 0); z-index: 15; max-height: 32vh; overflow-y: auto; }
}
@media (max-width: 520px) {
  .side { max-height: 22vh; }
  .side:has(.card-body) { max-height: 40vh; } /* a tapped word's card needs room for its meaning and the Save and Hear buttons */
  /* Two buttons per row instead of one button per row. */
  .tools { gap: 8px; }
  .tools .voice { flex: 1 1 100%; }
  .tools .voice .btn { flex: 1; }
  .tools > .btn { flex: 1 1 calc(50% - 8px); justify-content: center; }
}
@media (max-width: 640px) {
  .passage { font-size: calc(var(--read-size, 24px) * 0.8); }
  .head h2 { font-size: 28px; }
}
</style>
