<script setup>
// "My words": every passage the student has saved words from, with a Practice link. Reads this browser's storage only (see practice.js).
import { computed } from "vue";
import StateBlock from "../components/StateBlock.vue";
import { passageIndex } from "../api.js";
import { useResource } from "../useResource.js";
import { dueWords, loadState, safeStorage, storageKey } from "../practice.js";

const { data, loading, error, reload } = useResource(passageIndex);
const PREFIX = storageKey("");

function savedIds() {
  const store = safeStorage();
  if (!store) return [];
  try {
    return Array.from({ length: store.length }, (_, i) => store.key(i)).filter((k) => k?.startsWith(PREFIX)).map((k) => k.slice(PREFIX.length));
  } catch {
    return [];
  }
}

const rows = computed(() => {
  const now = Date.now();
  const byId = new Map((data.value ?? []).map((p) => [p.id, p]));
  return savedIds()
    .map((id) => {
      const state = loadState(id);
      const total = Object.keys(state.words).length;
      return { id, title: byId.get(id)?.title, total, due: dueWords(state, now).length };
    })
    .filter((r) => r.total > 0 && r.title)
    .sort((a, b) => b.due - a.due || a.title.localeCompare(b.title));
});
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>My words</h2>
        <p>Words you saved while reading. Practice them a little each day. They stay on this device only.</p>
      </div>
    </div>
    <StateBlock :loading="loading" :error="error" :empty="!rows.length" empty-text="No saved words yet. Open a passage, tap a word, and choose Save word." @retry="reload">
      <ul class="list">
        <li v-for="r in rows" :key="r.id" class="card row">
          <div>
            <h3>{{ r.title }}</h3>
            <p class="muted">{{ r.total }} saved {{ r.total === 1 ? "word" : "words" }} · {{ r.due }} ready to practise</p>
          </div>
          <a class="btn primary" :href="`#/practice/${encodeURIComponent(r.id)}`" :aria-label="`Practise words from ${r.title}`">Practice</a>
        </li>
      </ul>
    </StateBlock>
  </div>
</template>

<style scoped>
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.row { display: flex; align-items: center; justify-content: space-between; gap: var(--s2); flex-wrap: wrap; padding: var(--s2) var(--s3); }
h3 { font-size: 18px; overflow-wrap: anywhere; }
</style>
