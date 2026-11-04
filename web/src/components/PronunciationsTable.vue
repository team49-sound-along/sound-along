<script setup>
import { ref } from "vue";
import Icon from "./Icon.vue";
import { validatePronunciation } from "../pronunciations.js";

defineProps({ items: { type: Array, required: true }, busyWord: { type: String, default: "" }, error: { type: String, default: "" }, errorWord: { type: String, default: "" } });
const emit = defineEmits(["save", "remove"]);
const editing = ref("");
const draft = ref("");
const localError = ref("");
const confirming = ref("");

function edit(p) {
  editing.value = p.word;
  draft.value = p.respelling;
  localError.value = "";
  confirming.value = "";
}
function save(p) {
  const check = validatePronunciation({ word: p.word, respelling: draft.value });
  if (!check.valid) return (localError.value = check.errors.respelling || check.errors.word);
  emit("save", p.word, draft.value.trim(), () => (editing.value = ""));
}
</script>

<template>
  <div class="table-wrap" tabindex="0" role="region" aria-label="Pronunciation fixes">
    <table class="data">
      <caption class="sr-only">Pronunciation fixes</caption>
      <thead>
        <tr><th scope="col">Word</th><th scope="col">Respelling</th><th scope="col"><span class="sr-only">Actions</span></th></tr>
      </thead>
      <tbody>
        <tr v-for="p in items" :key="p.word">
          <th scope="row" class="title">{{ p.word }}</th>
          <td data-label="Respelling" class="resp">
            <div v-if="editing === p.word" class="edit">
              <label class="sr-only" :for="`pe-${p.word}`">Respelling for {{ p.word }}</label>
              <input :id="`pe-${p.word}`" v-model="draft" class="input" type="text" autocomplete="off" spellcheck="false" @keydown.enter.prevent="save(p)" @keydown.esc="editing = ''" />
              <p v-if="localError || (error && errorWord === p.word)" class="error-text" role="alert">{{ localError || error }}</p>
            </div>
            <code v-else>{{ p.respelling }}</code>
          </td>
          <td class="act">
            <div v-if="editing === p.word" class="row">
              <button class="btn primary" type="button" :disabled="busyWord === p.word" @click="save(p)">Save</button>
              <button class="btn" type="button" @click="editing = ''">Cancel</button>
            </div>
            <div v-else-if="confirming === p.word" class="row" role="group" :aria-label="`Confirm delete ${p.word}`">
              <span class="small">Delete this fix?</span>
              <button class="btn danger" type="button" @click="emit('remove', p.word); confirming = ''">Delete</button>
              <button class="btn" type="button" @click="confirming = ''">Cancel</button>
            </div>
            <div v-else class="row">
              <button class="btn" type="button" :aria-label="`Edit ${p.word}`" @click="edit(p)">Edit</button>
              <button class="btn ghost" type="button" :aria-label="`Delete ${p.word}`" @click="confirming = p.word"><Icon name="trash" :size="18" /></button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
@media (max-width: 640px) {
  .table-wrap :deep(table.data), .table-wrap :deep(tbody) { display: block; }
  .table-wrap :deep(thead) { display: none; }
  .table-wrap :deep(tr) { display: grid; grid-template-columns: minmax(0, 1fr); gap: 6px; padding: var(--s2); border-bottom: 1px solid var(--border); }
  .table-wrap :deep(tr:last-child) { border-bottom: 0; }
  .table-wrap :deep(td), .table-wrap :deep(th[scope="row"]) { display: flex; align-items: center; justify-content: space-between; gap: var(--s1); padding: 0; border: 0; min-width: 0; }
  .table-wrap :deep(td[data-label])::before { content: attr(data-label); font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); flex: none; }
  .table-wrap :deep(th[scope="row"]) { background: transparent; text-transform: none; letter-spacing: 0; font-size: 17px; white-space: normal; }
  .act { justify-content: flex-end; }
  .edit { flex: 1; }
}
.title { font-weight: 600; text-align: left; overflow-wrap: anywhere; }
.resp { overflow-wrap: anywhere; }
.act { text-align: right; }
.row { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.edit { display: grid; gap: 4px; min-width: 0; }
code { font-family: ui-monospace, Menlo, Consolas, monospace; }
</style>
