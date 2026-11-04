<script setup>
import { computed, ref } from "vue";
import Icon from "./Icon.vue";
import { isSpanish } from "../language.js";
import { passageSummary } from "../libraryMeta.js";
import { readTarget } from "../voices.js";

const props = defineProps({
  passage: { type: Object, required: true },
  canAssign: Boolean,
  canDelete: Boolean,
  busy: Boolean,
  list: Boolean,
});
const emit = defineEmits(["remove"]);
const summary = computed(() => passageSummary(props.passage));
const confirming = ref(false);
// What else goes with this card: the Library shows a passage's human narration and translations as part of the same card.
const alsoRemoved = computed(() => [
  ...(props.passage.humanId ? ["its human narration"] : []),
  ...(props.passage.translationLangs?.length ? ["its translation"] : []),
]);
function confirmRemove() {
  confirming.value = false;
  emit("remove", props.passage);
}
</script>

<template>
  <article class="pcard" :class="{ list }" :aria-labelledby="`p-${passage.id}`" :aria-describedby="`s-${passage.id}`">
    <div class="text">
      <h3 :id="`p-${passage.id}`">{{ passage.title }}</h3>
      <p v-if="isSpanish(passage) || passage.translationLangs?.length" class="badges">
        <span v-if="isSpanish(passage)" class="badge teal" lang="es" title="Spanish passage">Español</span>
        <span v-if="passage.translationLangs?.length" class="badge teal" title="Also available in another language">Also in {{ passage.translationLangs.map((l) => (l === "es" ? "Español" : "English")).join(", ") }}</span>
      </p>
      <p :id="`s-${passage.id}`" class="summary">{{ summary }}</p>
    </div>
    <div class="actions">
      <a class="btn primary" :href="`#/read/${encodeURIComponent(readTarget(passage))}`" :aria-label="`Read ${passage.title}`">
        <Icon name="book" :size="18" /> Read
      </a>
      <a v-if="canAssign" class="btn" :href="`#/assignments?passageId=${encodeURIComponent(passage.id)}`" :aria-label="`Assign ${passage.title}`">
        <Icon name="assign" :size="18" /> Assign
      </a>
      <button
        v-if="canDelete && !confirming" class="btn ghost" type="button" :disabled="busy"
        :aria-label="`Delete ${passage.title}`" @click="confirming = true"
      >
        <Icon name="trash" :size="18" /> {{ busy ? "Deleting…" : "Delete" }}
      </button>
    </div>
    <div v-if="canDelete && confirming" class="confirm" role="group" :aria-label="`Confirm delete ${passage.title}`">
      <p class="small">
        Delete &ldquo;{{ passage.title }}&rdquo; from the Library<template v-if="alsoRemoved.length">, with {{ alsoRemoved.join(" and ") }}</template>?
        Its assignments are deleted too. This cannot be undone.
      </p>
      <div class="confirm-actions">
        <button class="btn danger" type="button" @click="confirmRemove">Delete</button>
        <button class="btn" type="button" @click="confirming = false">Cancel</button>
      </div>
    </div>
  </article>
</template>

<style scoped>
.pcard { display: flex; flex-direction: column; gap: var(--s2); height: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: var(--s3); }
.text { display: grid; gap: 4px; min-width: 0; }
h3 { font-size: 20px; line-height: 1.3; font-weight: 700; overflow-wrap: anywhere; }
.badges { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; }
.summary { color: var(--muted); font-size: 14px; line-height: 1.5; }
.actions { display: flex; gap: var(--s1); flex-wrap: wrap; margin-top: auto; }
.confirm { display: grid; gap: var(--s1); border-top: 1px solid var(--border); padding-top: var(--s2); }
.confirm p { margin: 0; overflow-wrap: anywhere; }
.confirm-actions { display: flex; gap: var(--s1); flex-wrap: wrap; }
.pcard.list { flex-wrap: wrap; }
.pcard.list .confirm { flex: 1 1 100%; }
.pcard.list { flex-direction: row; align-items: center; justify-content: space-between; gap: var(--s3); height: auto; padding: var(--s2) var(--s3); }
.pcard.list .text { flex: 1 1 auto; }
.pcard.list .actions { flex: none; margin-top: 0; flex-wrap: nowrap; }
@media (max-width: 560px) {
  .pcard { padding: var(--s2); }
  .pcard.list { flex-direction: column; align-items: stretch; gap: var(--s2); }
  .pcard.list .actions { flex-wrap: wrap; }
  .actions .btn { flex: 1 1 auto; }
}
</style>
