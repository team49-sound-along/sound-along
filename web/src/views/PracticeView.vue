<script setup>
// Practice: "My words" flashcards (answer first, then reveal; spaced review) and a picture-match quiz. Progress stays in this browser only.
import { computed, onBeforeUnmount, ref } from "vue";
import StateBlock from "../components/StateBlock.vue";
import { audioUrl, fetchCards, fetchTiming } from "../api.js";
import { findWordCard } from "../cards.js";
import { route } from "../router.js";
import { useResource } from "../useResource.js";
import { approvedQuestions, buildPictureRound, clearState, dueWords, firstAlignedIndex, loadState, pictureWords, review, saveState } from "../practice.js";

const id = route.value.params.id;

async function fetchJson(url) {
  try {
    const res = await fetch(url);
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

async function load() {
  const timing = await fetchTiming(id);
  const pair = timing.pairId;
  const cards = (await fetchCards(id)) ?? (pair ? await fetchCards(pair) : null);
  const qdoc = (await fetchJson(`/data/${encodeURIComponent(id)}.questions.json`)) ?? (pair ? await fetchJson(`/data/${encodeURIComponent(pair)}.questions.json`) : null);
  return { timing, cards, questions: approvedQuestions(qdoc) };
}
const { data, loading, error, reload } = useResource(load);

// Progress is keyed by the AI passage id so the human-narrated variant shares it.
const practiceId = computed(() => (data.value?.timing.engine === "human" && data.value.timing.pairId ? data.value.timing.pairId : id));
const state = ref(loadState(id));
const saved = ref(true);
const now = () => Date.now();
const persist = () => (saved.value = saveState(practiceId.value, state.value));
const lang = computed(() => data.value?.timing.language || "en");
const title = computed(() => data.value?.timing.title ?? "");

// ---- flashcards ------------------------------------------------------------------------------------------------------------------
const anyway = ref(false);
const revealed = ref(false);
const queue = computed(() => dueWords(state.value, now(), anyway.value));
const starredCount = computed(() => Object.keys(state.value.words).length);
const currentKey = computed(() => queue.value[0] ?? null);
const current = computed(() => (currentKey.value && data.value ? findWordCard(data.value.cards, data.value.timing.vocab, currentKey.value) : null));
const audioIndex = computed(() => (currentKey.value && data.value ? firstAlignedIndex(data.value.timing.words, currentKey.value) : null));
const announce = ref("");

function answer(knew) {
  const key = currentKey.value;
  if (!key) return;
  state.value = review(state.value, key, knew, now());
  persist();
  revealed.value = false;
  announce.value = knew ? "Great. You will see this word again later." : "No problem. You will see it again now.";
}

let player = null;
function hear() {
  const word = data.value?.timing.words[audioIndex.value];
  if (!word) return;
  player?.pause();
  player = new Audio(audioUrl(id));
  player.currentTime = word.start_ms / 1000;
  player.play().catch(() => {});
  setTimeout(() => player?.pause(), Math.max(200, word.end_ms - word.start_ms) + 80);
}
onBeforeUnmount(() => player?.pause());

const confirmClear = ref(false);
function clearAll() {
  clearState(practiceId.value);
  state.value = loadState(practiceId.value);
  confirmClear.value = false;
  revealed.value = false;
  announce.value = "Your saved words were cleared on this device.";
}

// ---- picture match ---------------------------------------------------------------------------------------------------------------
const keys = computed(() => pictureWords(data.value?.cards?.words).map((c) => c.word));
const round = ref(null);
const picked = ref(null);
function nextRound() {
  picked.value = null;
  const words = data.value?.cards?.words;
  const options = keys.value.map((k) => buildPictureRound(words, k)).filter(Boolean);
  round.value = options.length ? options[Math.floor(Math.random() * options.length)] : null;
}
const canQuiz = computed(() => keys.value.length >= 3 && keys.value.some((k) => buildPictureRound(data.value?.cards?.words, k)));
function pick(i) {
  if (picked.value !== null) return;
  picked.value = i;
  announce.value = i === round.value.answerIndex ? "Correct!" : `Not quite. The picture of ${round.value.target.word} was the other one.`;
}
const started = ref(false);
function startQuiz() {
  started.value = true;
  nextRound();
}

// ---- practice questions (only ones a person approved) ------------------------------------------------------------------------------
const qIndex = ref(0);
const qPicked = ref(null);
const question = computed(() => data.value?.questions[qIndex.value] ?? null);
function pickQ(i) {
  if (qPicked.value === null) qPicked.value = i;
}
function nextQ() {
  qPicked.value = null;
  qIndex.value = (qIndex.value + 1) % data.value.questions.length;
}
</script>

<template>
  <div class="page practice">
    <StateBlock :loading="loading" :error="error" loading-label="Loading practice" @retry="reload">
      <template v-if="data">
        <p><a :href="`#/read/${encodeURIComponent(id)}`" class="btn">&larr; Back to the passage</a></p>
        <h2>Practice: <span :lang="lang">{{ title }}</span></h2>
        <p class="small muted">Your saved words stay on this device only. Nothing is sent anywhere.
          <span v-if="!saved"> Your browser is not saving progress right now.</span></p>
        <p class="sr-only" role="status" aria-live="polite">{{ announce }}</p>

        <section class="card" aria-labelledby="mw">
          <h3 id="mw">My words</h3>
          <p v-if="starredCount === 0" class="muted">No saved words yet. While reading, tap a word and press <strong>Save word</strong>. Then come back to practise.</p>
          <template v-else>
            <p class="small muted">{{ starredCount }} saved &middot; {{ queue.length }} to practise now</p>
            <div v-if="current" class="flash" aria-live="polite">
              <figure v-if="current.imageUrl" class="fpic"><img :src="current.imageUrl" alt="" width="120" height="120" /></figure>
              <p v-if="!revealed" class="prompt">{{ current.imageUrl ? "What is this? Say the word." : current.definition ? current.definition : "Say what this word means." }}</p>
              <template v-else>
                <p class="answer"><strong :lang="lang">{{ current.word }}</strong></p>
                <p v-if="current.definition" class="def">{{ current.definition }}</p>
                <p v-if="current.translation?.words?.length" class="small"><span class="label">{{ current.translation.lang === "es" ? "En español" : "In English" }}:</span> {{ current.translation.words.join(", ") }}</p>
                <p v-if="current.spanish?.length" class="small"><span class="label">En español:</span> {{ current.spanish.join(", ") }}</p>
              </template>
              <div class="row">
                <button v-if="!revealed" type="button" class="btn primary" @click="revealed = true">Show answer</button>
                <template v-else>
                  <button type="button" class="btn primary" @click="answer(true)">&#10003; I knew it</button>
                  <button type="button" class="btn" @click="answer(false)">&#8635; Not yet</button>
                </template>
                <button v-if="audioIndex !== null" type="button" class="btn" @click="hear">Hear the word</button>
              </div>
            </div>
            <div v-else>
              <p>Nothing is due right now. Well done!</p>
              <button type="button" class="btn" @click="anyway = true">Practise now anyway</button>
            </div>
            <p v-if="anyway && current" class="small"><button type="button" class="btn" @click="anyway = false">Only practise what is due</button></p>
          </template>
          <p class="small">
            <button v-if="!confirmClear" type="button" class="btn" :disabled="starredCount === 0" @click="confirmClear = true">Clear my words</button>
            <span v-else>Remove all saved words on this device?
              <button type="button" class="btn" @click="clearAll">Yes, clear them</button>
              <button type="button" class="btn" @click="confirmClear = false">No</button></span>
          </p>
        </section>

        <section v-if="canQuiz" class="card" aria-labelledby="pm">
          <h3 id="pm">Picture match</h3>
          <button v-if="!started" type="button" class="btn primary" @click="startQuiz">Start</button>
          <div v-else-if="round">
            <p class="prompt">Which picture is <strong :lang="lang">{{ round.target.word }}</strong>?</p>
            <div class="choices" role="group" aria-label="Pictures">
              <button v-for="(c, i) in round.choices" :key="c.imageUrl" type="button" class="choice" :disabled="picked !== null" :aria-label="`Picture ${i + 1}`" @click="pick(i)">
                <img :src="c.imageUrl" alt="" width="96" height="96" />
                <span v-if="picked !== null && i === round.answerIndex" class="mark">&#10003; Correct answer</span>
                <span v-else-if="picked === i" class="mark">&#10007; Your choice</span>
              </button>
            </div>
            <p v-if="picked !== null" class="feedback">{{ picked === round.answerIndex ? "Correct!" : `Not quite: the right picture is marked.` }}
              <button type="button" class="btn primary" @click="nextRound">Next</button></p>
          </div>
        </section>

        <section v-if="question" class="card" aria-labelledby="pq">
          <h3 id="pq">Practice questions</h3>
          <p class="small muted">Checked by a person before you see them.</p>
          <p class="prompt">{{ question.question }}</p>
          <div class="qchoices" role="group" aria-label="Answers">
            <button v-for="(c, i) in question.choices" :key="i" type="button" class="btn" :disabled="qPicked !== null" @click="pickQ(i)">
              {{ c }}<span v-if="qPicked !== null && i === question.answerIndex"> &#10003; correct</span><span v-else-if="qPicked === i"> &#10007; your choice</span>
            </button>
          </div>
          <p v-if="qPicked !== null"><button type="button" class="btn primary" @click="nextQ">Next question</button></p>
        </section>
      </template>
    </StateBlock>
  </div>
</template>

<style scoped>
.practice { max-width: 760px; gap: var(--s2); }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: var(--s3); display: grid; gap: var(--s2); }
.flash { display: grid; gap: var(--s1); justify-items: start; }
.fpic { margin: 0; }
.fpic img { width: 120px; height: 120px; object-fit: contain; background: var(--border); border-radius: 12px; padding: 8px; box-sizing: border-box; }
.prompt { font-size: 20px; }
.answer { font-size: 28px; }
.row { display: flex; flex-wrap: wrap; gap: var(--s1); }
.choices { display: flex; flex-wrap: wrap; gap: var(--s2); }
.choice { display: grid; gap: 4px; justify-items: center; padding: 8px; border: 2px solid var(--border); border-radius: 12px; background: var(--surface); cursor: pointer; }
.choice:focus-visible { outline: 3px solid var(--accent, #2c6e63); outline-offset: 2px; }
.choice img { background: var(--border); border-radius: 8px; padding: 6px; box-sizing: border-box; }
.mark { font-size: 14px; font-weight: 700; }
.qchoices { display: grid; gap: var(--s1); justify-items: start; }
.label { font-weight: 700; }
</style>
