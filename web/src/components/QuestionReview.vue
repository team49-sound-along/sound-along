<script setup>
// One passage's question draft: every question starts undecided. Only the questions marked Approved are sent when the teacher publishes.
import { computed, ref, watch } from "vue";
import QuestionCard from "./QuestionCard.vue";
import StateBlock from "./StateBlock.vue";
import { api, fetchQuestions, fetchTiming } from "../api.js";
import { approvedQuestions } from "../quiz.js";
import { approvedPayload, canPublish, counts, loadReview, saveReview, sentenceText, setEdit, setStatus } from "../questionReview.js";
import { useResource } from "../useResource.js";

const props = defineProps({ passageId: { type: String, required: true } });

async function load() {
  const [view, timing, published] = await Promise.all([api.questionDraft(props.passageId), fetchTiming(props.passageId).catch(() => null), fetchQuestions(props.passageId)]);
  return { view, timing, published };
}
const { data, loading, error, reload } = useResource(load);

const review = ref({ status: {}, edits: {} });
watch(data, (d) => { if (d) review.value = loadReview(props.passageId, undefined, d.view); }, { immediate: true });

const lang = computed(() => (data.value?.timing?.language === "es" ? "es" : "en"));
const tally = computed(() => (data.value ? counts(data.value.view, review.value) : { approved: 0, rejected: 0, pending: 0 }));
const publishable = computed(() => data.value !== null && canPublish(data.value.view, review.value));
const publishedCount = computed(() => approvedQuestions(data.value?.published).length);
const sentenceFor = (q) => sentenceText(data.value?.timing?.words, q.evidenceSentence);

function update(next) {
  review.value = next;
  saveReview(props.passageId, next, undefined, data.value.view);
}

const publishing = ref(false);
const failure = ref("");
const done = ref("");
async function publish() {
  if (!publishable.value || publishing.value) return;
  publishing.value = true;
  failure.value = "";
  done.value = "";
  try {
    const res = await api.publishQuestions(props.passageId, approvedPayload(data.value.view, review.value));
    done.value = `Published ${res.published} question${res.published === 1 ? "" : "s"}. Students can now take the quiz.`;
    data.value = { ...data.value, published: await fetchQuestions(props.passageId) };
  } catch (e) {
    failure.value = e?.message || "We could not publish. Please try again.";
  } finally {
    publishing.value = false;
  }
}
</script>

<template>
  <div class="page narrow">
    <p><a href="#/questions" class="btn">&larr; All question drafts</a></p>
    <StateBlock :loading="loading" :error="error" loading-label="Loading questions" @retry="reload">
      <template v-if="data">
        <div class="page-head">
          <div>
            <h2>Questions for <span :lang="lang">{{ data.view.title }}</span></h2>
            <p>Read each question against the passage. Approve the good ones, reject the rest, fix small wording problems with Edit text.</p>
          </div>
        </div>
        <p class="notice warn" role="note">These questions were written automatically and have <strong>not been checked by a person yet</strong>. The automatic checks are hints, not a review. Students see only what you approve and publish.</p>
        <p v-if="data.view.skipped" class="small muted">{{ data.view.skipped }} unusable question{{ data.view.skipped === 1 ? " was" : "s were" }} left out.</p>
        <p v-if="publishedCount" class="small"><span class="badge teal">Published: {{ publishedCount }} for students</span> Publishing again replaces the published set with your approved questions.</p>

        <ol class="cards">
          <QuestionCard
            v-for="(q, n) in data.view.questions" :key="q.id" :question="q" :number="n + 1" :lang="lang" :sentence="sentenceFor(q)"
            :status="review.status[q.id] ?? 'pending'" :edit="review.edits[q.id] ?? null"
            @status="update(setStatus(review, q.id, $event))" @edit="update(setEdit(review, q.id, $event))"
          />
        </ol>

        <section class="card publish" aria-labelledby="pub-h">
          <h3 id="pub-h">Publish</h3>
          <p id="pub-hint" class="small" role="status">{{ tally.approved }} approved &middot; {{ tally.rejected }} rejected &middot; {{ tally.pending }} not decided.
            <span v-if="!publishable"> Approve at least one question to publish.</span>
            <span v-else-if="tally.pending"> Questions you have not decided are not published.</span></p>
          <p v-if="failure" class="notice error" role="alert">{{ failure }}</p>
          <p v-if="done" class="notice ok" role="status">{{ done }} <a :href="`#/quiz/${encodeURIComponent(passageId)}`">Try the quiz</a></p>
          <div class="row">
            <button type="button" class="btn primary" :disabled="!publishable || publishing" aria-describedby="pub-hint" @click="publish">{{ publishing ? "Publishing…" : "Publish approved questions" }}</button>
          </div>
        </section>
      </template>
    </StateBlock>
  </div>
</template>

<style scoped>
.cards { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.publish { display: grid; gap: var(--s1); position: sticky; bottom: var(--s1); }
.row { display: flex; flex-wrap: wrap; gap: var(--s1); }
@media (max-width: 640px) { .publish { position: static; } }
</style>
