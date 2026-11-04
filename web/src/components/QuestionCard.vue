<script setup>
// One draft question: choices with the correct one marked, the evidence, the automatic checks in plain words, and Approve / Reject / Edit text.
import { computed, nextTick, ref } from "vue";
import { describeChecks, validateEdit } from "../questionReview.js";

const props = defineProps({
  question: { type: Object, required: true },
  number: { type: Number, required: true },
  status: { type: String, default: "pending" },
  edit: { type: Object, default: null },
  sentence: { type: String, default: "" },
  lang: { type: String, default: "en" },
});
const emit = defineEmits(["status", "edit"]);

const shown = computed(() => props.edit ?? props.question);
const checks = computed(() => describeChecks(props.question.checks));
const SKILLS = { literal: "Recall: the answer is stated in the passage", inferential: "Inference: the answer is worked out from the passage" };
const STATUS_TEXT = { pending: "Not decided", approved: "Approved", rejected: "Rejected" };

const editing = ref(false);
const draftQuestion = ref("");
const draftChoices = ref([]);
const problem = ref("");
const firstField = ref(null);
const editButton = ref(null);

function startEdit() {
  draftQuestion.value = shown.value.question;
  draftChoices.value = [...shown.value.choices];
  problem.value = "";
  editing.value = true;
  nextTick(() => firstField.value?.focus());
}
function saveEdit() {
  const next = { question: draftQuestion.value.replace(/\s+/g, " ").trim(), choices: draftChoices.value.map((c) => c.replace(/\s+/g, " ").trim()) };
  problem.value = validateEdit(props.question, next);
  if (problem.value) return;
  emit("edit", next);
  editing.value = false;
  nextTick(() => editButton.value?.focus());
}
function cancelEdit() {
  editing.value = false;
  nextTick(() => editButton.value?.focus());
}
const toggle = (target) => emit("status", props.status === target ? "pending" : target);
</script>

<template>
  <li class="card q" :class="status" :aria-labelledby="`qc-${question.id}`">
    <div class="top">
      <h3 :id="`qc-${question.id}`">Question {{ number }}</h3>
      <span class="badge" :class="{ teal: status === 'approved' }">{{ status === "approved" ? "✓ " : status === "rejected" ? "✗ " : "" }}{{ STATUS_TEXT[status] }}</span>
    </div>
    <p class="small muted">{{ SKILLS[question.skill] }}</p>

    <template v-if="!editing">
      <p class="prompt" :lang="lang">{{ shown.question }}</p>
      <ul class="choices" :lang="lang">
        <li v-for="(c, i) in shown.choices" :key="i" :class="{ right: i === question.answerIndex }">
          <span class="text">{{ c }}</span>
          <span v-if="i === question.answerIndex" class="tag">&#10003; Correct answer</span>
        </li>
      </ul>
    </template>
    <form v-else class="editor" @submit.prevent="saveEdit">
      <div class="field">
        <label :for="`eq-${question.id}`">Question</label>
        <textarea :id="`eq-${question.id}`" ref="firstField" v-model="draftQuestion" class="input" rows="2" maxlength="300" :lang="lang"></textarea>
      </div>
      <div v-for="(c, i) in draftChoices" :key="i" class="field">
        <label :for="`ec-${question.id}-${i}`">Answer {{ i + 1 }}<span v-if="i === question.answerIndex"> (the correct answer)</span></label>
        <input :id="`ec-${question.id}-${i}`" v-model="draftChoices[i]" class="input" type="text" maxlength="160" :lang="lang" />
      </div>
      <p v-if="problem" class="error-text" role="alert">{{ problem }}</p>
      <p class="small muted">You can fix wording here. The correct answer stays where it is.</p>
      <div class="row">
        <button type="submit" class="btn primary">Save text</button>
        <button type="button" class="btn" @click="cancelEdit">Cancel</button>
      </div>
    </form>

    <div class="evidence">
      <p class="small"><strong>Where the passage says it:</strong> sentence {{ question.evidenceSentence + 1 }}.</p>
      <blockquote v-if="sentence" class="sentence" :lang="lang">{{ sentence }}</blockquote>
      <p v-if="question.evidenceQuote" class="small muted"><span class="sr-only">Quoted evidence: </span>Quoted: &ldquo;<span :lang="lang">{{ question.evidenceQuote }}</span>&rdquo;</p>
    </div>

    <ul v-if="checks.length" class="checks" aria-label="Automatic checks">
      <li v-for="(c, i) in checks" :key="i" :class="c.tone"><span aria-hidden="true">{{ c.tone === "ok" ? "✓" : "!" }}</span> {{ c.text }}</li>
    </ul>

    <div class="row actions">
      <button type="button" class="btn" :class="{ primary: status === 'approved' }" :aria-pressed="status === 'approved'" @click="toggle('approved')">Approve</button>
      <button type="button" class="btn" :class="{ danger: status === 'rejected' }" :aria-pressed="status === 'rejected'" @click="toggle('rejected')">Reject</button>
      <button ref="editButton" type="button" class="btn" :disabled="editing" @click="startEdit">Edit text</button>
    </div>
  </li>
</template>

<style scoped>
.q { display: grid; gap: var(--s1); list-style: none; }
.q.approved { border-color: var(--primary); }
.q.rejected { opacity: 0.85; }
.top { display: flex; justify-content: space-between; align-items: center; gap: var(--s1); }
.prompt { font-size: 18px; font-weight: 600; }
.choices { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
.choices li { display: flex; flex-wrap: wrap; gap: 4px 12px; padding: 8px 12px; border: 1px solid var(--border); border-radius: var(--r-sm); }
.choices li.right { border-color: var(--ok); background: var(--ok-soft); }
.choices .text { flex: 1 1 8ch; min-width: 0; overflow-wrap: anywhere; }
.tag { font-size: 14px; font-weight: 700; color: var(--ok); }
.evidence { display: grid; gap: 4px; }
.sentence { margin: 0; padding: 8px 12px; border-left: 4px solid var(--hl); background: var(--surface-2); border-radius: 0 var(--r-sm) var(--r-sm) 0; }
.checks { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; font-size: 14px; }
.checks li.ok { color: var(--ok); }
.checks li.warn { color: var(--on-hl); background: var(--warn-soft); padding: 6px 10px; border-radius: var(--r-sm); }
.editor { display: grid; gap: var(--s1); }
.row { display: flex; flex-wrap: wrap; gap: var(--s1); }
.actions { margin-top: var(--s1); }
</style>
