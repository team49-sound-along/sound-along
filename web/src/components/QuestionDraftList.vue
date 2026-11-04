<script setup>
// Passages that have question drafts. Nothing here is visible to students: only questions a teacher approves and publishes are.
import StateBlock from "./StateBlock.vue";
import { api, fetchQuestions } from "../api.js";
import { approvedQuestions } from "../quiz.js";
import { useResource } from "../useResource.js";

async function load() {
  const drafts = await api.questionDrafts();
  return Promise.all(drafts.map(async (d) => ({ ...d, published: approvedQuestions(await fetchQuestions(d.passageId)).length })));
}
const { data, loading, error, reload } = useResource(load);
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>Question review</h2>
        <p>Practice questions written automatically for passages. Read each one, approve or reject it, then publish the ones you approve.</p>
      </div>
    </div>
    <p class="notice warn" role="note">These questions have <strong>not been checked by a person yet</strong>. Students see nothing until you publish.</p>
    <StateBlock :loading="loading" :error="error" :empty="!loading && !error && !(data && data.length)" empty-title="No question drafts" empty-text="When questions are written for a passage, they will wait here for you." loading-label="Loading questions" @retry="reload">
      <ul class="list">
        <li v-for="d in data" :key="d.passageId" class="card item">
          <div class="info">
            <h3><span :lang="d.language">{{ d.title }}</span></h3>
            <p class="small muted">
              {{ d.questionCount }} question{{ d.questionCount === 1 ? "" : "s" }}
              <template v-if="d.flaggedCount"> &middot; {{ d.flaggedCount }} flagged by an automatic check</template>
              <template v-if="d.generatedOn"> &middot; written {{ d.generatedOn }}</template>
            </p>
            <p class="small"><span class="badge" :class="d.published ? 'teal' : ''">{{ d.published ? `Published: ${d.published} for students` : "Not published" }}</span></p>
          </div>
          <a class="btn primary" :href="`#/questions/${encodeURIComponent(d.passageId)}`">Review<span class="sr-only"> {{ d.title }}</span></a>
        </li>
      </ul>
    </StateBlock>
  </div>
</template>

<style scoped>
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); max-width: 760px; }
.item { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--s2); }
.info { display: grid; gap: 4px; min-width: 0; }
</style>
