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
const href = (id) => `#/read/${encodeURIComponent(id)}`;
</script>

<template>
  <nav v-if="info" class="parts" :aria-label="`Parts of ${info.title || 'this document'}`">
    <p v-if="showLabel" class="where"><strong>Part {{ info.index }} of {{ info.total }}</strong><span v-if="info.title" class="muted"> &middot; {{ info.title }}</span></p>
    <div class="links">
      <a v-if="prev?.state === 'ready'" class="btn" :href="href(prev.id)">&larr; Previous part</a>
      <a v-if="next?.state === 'ready'" class="btn primary" :href="href(next.id)">Next part &rarr;</a>
      <span v-else-if="next?.state === 'pending'" class="small muted" role="status">
        The next part is still being created.
        <button type="button" class="linklike" @click="load">Check again</button>
      </span>
    </div>
  </nav>
</template>

<style scoped>
.parts { display: grid; gap: var(--s1); }
.where { margin: 0; }
.links { display: flex; gap: var(--s1); flex-wrap: wrap; align-items: center; }
.linklike { background: none; border: 0; padding: 0; color: var(--primary); text-decoration: underline; cursor: pointer; font: inherit; min-height: 32px; }
</style>
