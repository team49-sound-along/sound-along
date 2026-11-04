<script setup>
// Practice: "My words" flashcards (answer first, then reveal; spaced review) and practice questions a person approved. Progress stays in this browser only.
import { computed, onBeforeUnmount, ref } from "vue";
import StateBlock from "../components/StateBlock.vue";
import { audioUrl, fetchCards, fetchTiming } from "../api.js";
import { findWordCard } from "../cards.js";
import { route } from "../router.js";
import { useResource } from "../useResource.js";
import { approvedQuestions, clearState, dueWords, firstAlignedIndex, loadState, review, saveState } from "../practice.js";

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
const current = computed(() => (currentKey.value && data.value ? (findWordCard(data.value.cards, data.value.timing.vocab, currentKey.value) ?? { word: currentKey.value }) : null));
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
              <figure v-if="current.imageUrl" class="fpic"><img :src="current.imageUrl" alt="" :width="current.imageWidth || undefined" :height="current.imageHeight || undefined" /></figure>
              <p v-if="!revealed" class="prompt">{{ current.imageUrl ? "What is this? Say the word." : current.definition ? current.definition : audioIndex !== null ? "Listen, then say the word and what it means." : "Say what this word means." }}</p>
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
.fpic img { display: block; width: auto; max-width: 100%; height: auto; max-height: 200px; background: var(--border); border-radius: 12px; }
.prompt { font-size: 20px; }
.answer { font-size: 28px; }
.row { display: flex; flex-wrap: wrap; gap: var(--s1); }
.qchoices { display: grid; gap: var(--s1); justify-items: start; }
.label { font-weight: 700; }
</style>
