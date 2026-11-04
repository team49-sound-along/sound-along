<script setup>
// Passage quiz: one question at a time, immediate feedback, "Show me where", and a score with a review. Questions are only ever from a
// document a person approved. Results stay in this browser (see quiz.js); nothing is sent anywhere.
import { computed, nextTick, ref, watch } from "vue";
import StateBlock from "../components/StateBlock.vue";
import { fetchTiming } from "../api.js";
import { langAttr } from "../language.js";
import { evidenceHref, loadResult, prepareAttempt, recordResult, scoreAttempt, clearResult } from "../quiz.js";
import { loadQuiz } from "../quizLoad.js";
import { attemptFor, restartAttempt } from "../quizSession.js";
import { route } from "../router.js";
import { useResource } from "../useResource.js";

const id = route.value.params.id;
const LANGUAGE_WORDS = { en: "English", es: "Spanish" };

async function load() {
  const timing = await fetchTiming(id);
  return { timing, quiz: await loadQuiz(id, timing) };
}
const { data, loading, error, reload } = useResource(load);

const attempt = ref(null);
const saved = ref(true);
const result = ref(null);
const heading = ref(null);
const next = ref(null);
const announce = ref("");

const quiz = computed(() => data.value?.quiz ?? null);
const title = computed(() => data.value?.timing.title ?? "");
const passageLang = computed(() => langAttr(data.value?.timing.language));
const questionLang = computed(() => langAttr(quiz.value?.otherLanguage ?? data.value?.timing.language));
const questions = computed(() => (quiz.value && attempt.value ? prepareAttempt(quiz.value.questions, attempt.value.seed) : []));
const total = computed(() => questions.value.length);
const current = computed(() => questions.value[attempt.value?.index] ?? null);
const picked = computed(() => (current.value ? (attempt.value.answers[current.value.id] ?? null) : null));
const answered = computed(() => picked.value !== null);
const score = computed(() => scoreAttempt(questions.value, attempt.value?.answers ?? {}));
const isLast = computed(() => attempt.value?.index === total.value - 1);
const backHref = `#/read/${encodeURIComponent(id)}`;
const otherName = computed(() => LANGUAGE_WORDS[quiz.value?.otherLanguage] ?? "");

// Start (or resume) the attempt as soon as the questions are known.
watch(
  quiz,
  (found) => {
    if (!found) return;
    const ids = found.questions.map((q) => q.id);
    result.value = loadResult(found.docId);
    attempt.value = attemptFor(found.docId, ids);
    // a finished attempt with no recorded score cannot be shown as a score: start over
    if (attempt.value.finished && !result.value) attempt.value = restartAttempt(found.docId, ids);
  },
  { immediate: true },
);

const refocus = (el) => nextTick(() => el.value?.focus());

function choose(index) {
  if (answered.value || !current.value) return;
  attempt.value.answers = { ...attempt.value.answers, [current.value.id]: index };
  announce.value = index === current.value.answerIndex ? "Correct." : `Not quite. The correct answer is: ${current.value.choices[current.value.answerIndex]}.`;
  refocus(next);
}

function advance() {
  if (!answered.value) return;
  announce.value = "";
  if (isLast.value) {
    attempt.value.finished = true;
    saved.value = recordResult(quiz.value.docId, scoreAttempt(questions.value, attempt.value.answers), Date.now());
    result.value = loadResult(quiz.value.docId);
  } else {
    attempt.value.index += 1;
  }
  refocus(heading);
}

function retry() {
  attempt.value = restartAttempt(quiz.value.docId, quiz.value.questions.map((q) => q.id));
  announce.value = "";
  refocus(heading);
}

const confirmClear = ref(false);
function clearSaved() {
  clearResult(quiz.value.docId);
  result.value = null;
  confirmClear.value = false;
  announce.value = "Your quiz scores were cleared on this device.";
}

const href = (q) => evidenceHref(quiz.value.readerId, q.evidenceSentence);
const optionOf = (item) => questions.value.find((q) => q.id === item.id);
</script>

<template>
  <div class="page quiz">
    <StateBlock :loading="loading" :error="error" :empty="Boolean(data) && !quiz" empty-title="No quiz for this passage yet" empty-text="A quiz appears here once a teacher has checked and published questions for this passage." loading-label="Loading quiz" @retry="reload">
      <template v-if="data && quiz && attempt">
        <p><a :href="backHref" class="btn">&larr; Back to the passage</a></p>
        <h2 ref="heading" tabindex="-1">Quiz: <span :lang="passageLang">{{ title }}</span></h2>
        <p class="small muted">Your answers and scores stay on this device only. Nothing is sent anywhere. <span v-if="!saved">Your browser is not saving scores right now.</span></p>
        <p v-if="quiz.otherLanguage" class="notice warn" role="note">Questions for this passage are only available in {{ otherName }}, so this quiz is in {{ otherName }}.</p>
        <p class="sr-only" role="status" aria-live="polite">{{ announce }}</p>

        <section v-if="!attempt.finished && current" class="card q" aria-labelledby="qh">
          <div class="progress-row">
            <p id="qh" class="eyebrow">Question {{ attempt.index + 1 }} of {{ total }}</p>
            <progress class="bar" :value="attempt.index + (answered ? 1 : 0)" :max="total" :aria-label="`Quiz progress: ${attempt.index + (answered ? 1 : 0)} of ${total} answered`"></progress>
          </div>
          <div class="choices" role="group" aria-labelledby="qprompt" :lang="questionLang">
            <p id="qprompt" class="prompt">{{ current.question }}</p>
            <button
              v-for="(c, i) in current.choices" :key="`${current.id}-${i}`" type="button" class="choice" :disabled="answered"
              :class="{ right: answered && i === current.answerIndex, wrong: answered && picked === i && i !== current.answerIndex, picked: picked === i }"
              @click="choose(i)"
            >
              <span class="dot" aria-hidden="true"></span>
              <span class="text">{{ c }}</span>
              <span v-if="answered && i === current.answerIndex" class="tag">&#10003; Correct answer</span>
              <span v-else-if="answered && picked === i" class="tag">&#10007; Your answer</span>
            </button>
          </div>
          <div class="feedback" aria-live="polite">
            <template v-if="answered">
              <p v-if="picked === current.answerIndex" class="verdict good"><strong>Correct!</strong> Well done.</p>
              <p v-else class="verdict bad"><strong>Not quite.</strong> The correct answer is <span :lang="questionLang">&ldquo;{{ current.choices[current.answerIndex] }}&rdquo;</span>.</p>
              <p v-if="href(current)" class="small"><a :href="href(current)" class="btn">Show me where</a> <span class="muted">Opens the passage at that sentence. Use the Back button to return to your quiz.</span></p>
            </template>
          </div>
          <p><button ref="next" type="button" class="btn primary" :disabled="!answered" @click="advance">{{ isLast ? "See my score" : "Next question" }}</button></p>
        </section>

        <section v-else-if="attempt.finished" class="card" aria-labelledby="sh">
          <h3 id="sh">Your score: {{ score.correct }} of {{ score.total }}</h3>
          <p v-if="result && result.attempts > 1" class="small muted">Best on this device: {{ result.best.correct }} of {{ result.best.total }}. Tries: {{ result.attempts }}.</p>
          <ol class="review">
            <li v-for="(item, n) in score.items" :key="item.id" :class="{ good: item.correct, bad: !item.correct }">
              <p class="rq" :lang="questionLang"><span class="sr-only">Question {{ n + 1 }}: </span>{{ optionOf(item).question }}</p>
              <p class="small"><strong>{{ item.correct ? "\u2713 Correct" : "\u2717 Not quite" }}.</strong>
                <span v-if="!item.correct && item.picked !== null"> You chose <span :lang="questionLang">&ldquo;{{ optionOf(item).choices[item.picked] }}&rdquo;</span>.</span>
                <span v-if="!item.correct"> The answer is <span :lang="questionLang">&ldquo;{{ optionOf(item).choices[optionOf(item).answerIndex] }}&rdquo;</span>.</span>
                <span v-else> <span :lang="questionLang">&ldquo;{{ optionOf(item).choices[item.picked] }}&rdquo;</span></span>
              </p>
              <p v-if="href(optionOf(item))" class="small"><a :href="href(optionOf(item))">Show me where<span class="sr-only"> for question {{ n + 1 }}</span></a></p>
            </li>
          </ol>
          <div class="row">
            <button type="button" class="btn primary" @click="retry">Retry</button>
            <a :href="backHref" class="btn">Back to passage</a>
          </div>
          <p class="small">
            <button v-if="!confirmClear" type="button" class="btn" :disabled="!result" @click="confirmClear = true">Clear my quiz scores</button>
            <span v-else>Remove saved scores on this device?
              <button type="button" class="btn" @click="clearSaved">Yes, clear them</button>
              <button type="button" class="btn" @click="confirmClear = false">No</button></span>
          </p>
        </section>
      </template>
    </StateBlock>
  </div>
</template>

<style scoped>
.quiz { gap: var(--s2); }
.quiz > * { max-width: 760px; }
h2:focus { outline: none; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: var(--s3); display: grid; gap: var(--s2); }
.progress-row { display: grid; gap: 6px; }
.bar { width: 100%; height: 10px; accent-color: var(--primary); }
.choices { display: grid; gap: var(--s1); }
.prompt { font-size: 20px; line-height: 1.4; margin-bottom: var(--s1); font-weight: 600; }
.choice { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; width: 100%; min-height: 56px; padding: 12px var(--s2); border: 2px solid var(--border); border-radius: var(--r-sm); background: var(--surface); color: var(--text); cursor: pointer; font-size: 18px; text-align: left; }
.choice:hover:not(:disabled) { background: var(--surface-2); }
.choice .dot { width: 22px; height: 22px; flex: none; border: 2px solid var(--muted); border-radius: 50%; background: var(--surface); }
.choice .text { flex: 1 1 8ch; min-width: 0; overflow-wrap: anywhere; }
.choice .tag { font-size: 14px; font-weight: 700; }
.choice.picked { border-color: var(--primary); background: var(--primary-soft); }
.choice.picked .dot { border-color: var(--primary); background: radial-gradient(circle, var(--primary) 0 45%, var(--surface) 50%); }
.choice.right { border-color: var(--ok); background: var(--ok-soft); color: var(--ok); }
.choice.wrong { border-color: var(--danger); background: var(--danger-soft); color: var(--danger); }
.choice:disabled { cursor: default; opacity: 1; }
.verdict { font-size: 18px; }
.verdict.good { color: var(--ok); }
.verdict.bad { color: var(--danger); }
.feedback { min-height: 1.5em; display: grid; gap: var(--s1); }
.review { margin: 0; padding: 0; list-style: none; display: grid; gap: var(--s2); }
.review li { display: grid; gap: 4px; padding-left: var(--s2); border-left: 4px solid var(--border); }
.review li.good { border-left-color: var(--ok); }
.review li.bad { border-left-color: var(--danger); }
.rq { font-weight: 600; }
.row { display: flex; flex-wrap: wrap; gap: var(--s1); }
</style>
