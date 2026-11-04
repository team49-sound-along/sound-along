<script setup>
// "Part 2 of 4" with links to the previous and next part of a long document. A part that is still being created says so instead of leading nowhere.
import { computed, ref, watch } from "vue";
import { fetchTiming } from "../api.js";
import { neighborPart, seriesInfo } from "../series.js";

const props = defineProps({ timing: { type: Object, required: true }, showLabel: { type: Boolean, default: true } });
const info = computed(() => seriesInfo(props.timing));
const prev = ref(null);
const next = ref(null);

async function load() {
  if (!info.value) {
    prev.value = null;
    next.value = null;
    return;
  }
  [prev.value, next.value] = await Promise.all([neighborPart(props.timing, -1, fetchTiming), neighborPart(props.timing, 1, fetchTiming)]);
}
watch(() => props.timing?.id, load, { immediate: true });
const TEXT = {
  en: { part: "Part", of: "of", prev: "Previous part", next: "Next part", pending: "The next part is still being created.", check: "Check again" },
  es: { part: "Parte", of: "de", prev: "Parte anterior", next: "Parte siguiente", pending: "La siguiente parte todavía se está creando.", check: "Comprobar de nuevo" },
};
const t = computed(() => TEXT[props.timing?.language === "es" ? "es" : "en"]);
const href = (id) => `#/read/${encodeURIComponent(id)}`;
</script>

<template>
  <nav v-if="info" class="parts" :class="{ top: showLabel }" :lang="timing.language === 'es' ? 'es' : 'en'" :aria-label="`${showLabel ? 'Parts of' : 'More parts of'} ${info.title || 'this document'}`">
    <p v-if="showLabel" class="where"><strong>{{ t.part }} {{ info.index }} {{ t.of }} {{ info.total }}</strong><span v-if="info.title" class="muted"> &middot; {{ info.title }}</span></p>
    <div class="links">
      <a v-if="prev?.state === 'ready'" class="btn" :href="href(prev.id)">&larr; {{ t.prev }}</a>
      <a v-if="next?.state === 'ready'" class="btn primary" :href="href(next.id)">{{ t.next }} &rarr;</a>
      <span v-else-if="next?.state === 'pending'" class="small muted" role="status">
        {{ t.pending }}
        <button type="button" class="linklike" @click="load">{{ t.check }}</button>
      </span>
    </div>
  </nav>
</template>

<style scoped>
.parts { display: grid; gap: var(--s1); }
.where { margin: 0; }
/* On a phone the passage should start high on the screen: the top bar keeps only "Part 1 of 4", and the buttons are at the end of the passage. */
@media (max-width: 640px) { .parts.top .links { display: none; } .parts.top .where { font-size: 14px; } }
.links { display: flex; gap: var(--s1); flex-wrap: wrap; align-items: center; }
.linklike { background: none; border: 0; padding: 0; color: var(--primary); text-decoration: underline; cursor: pointer; font: inherit; min-height: 32px; }
</style>
