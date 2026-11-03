<script setup>
import { computed, ref } from "vue";
import Icon from "../components/Icon.vue";
import StateBlock from "../components/StateBlock.vue";
import PassageCard from "../components/PassageCard.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import { filterPassages } from "../assignments.js";
import { groupVariants } from "../voices.js";
import { role } from "../session.js";

const { data, loading, error, reload } = useResource(api.passages);
const query = ref("");
const layout = ref("grid");
const passages = computed(() => groupVariants(data.value ?? []));
const shown = computed(() => filterPassages(passages.value, query.value));
const isTeacher = computed(() => role.value === "teacher");
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>Library</h2>
        <p>Every passage has narrated audio with word-level timing. Tap any word while reading to hear it again from there.</p>
      </div>
      <div class="tools">
        <div class="search">
          <Icon name="search" :size="18" />
          <label class="sr-only" for="q">Search passages by title</label>
          <input id="q" v-model="query" class="input" type="search" placeholder="Search passages" autocomplete="off" />
        </div>
        <div class="seg" role="group" aria-label="Layout">
          <button type="button" :aria-pressed="layout === 'grid'" @click="layout = 'grid'"><Icon name="grid" :size="18" /><span class="sr-only">Grid</span></button>
          <button type="button" :aria-pressed="layout === 'list'" @click="layout = 'list'"><Icon name="list" :size="18" /><span class="sr-only">List</span></button>
        </div>
      </div>
    </div>

    <StateBlock
      :loading="loading"
      :error="error"
      :empty="!passages.length"
      loading-label="Loading passages"
      empty-title="No passages yet"
      empty-text="Generate your first passage from any text."
      @retry="reload"
    >
      <p v-if="!shown.length" class="card muted" role="status">No passages match &ldquo;{{ query }}&rdquo;.</p>
      <ul v-else class="grid" :class="layout" aria-label="Passages">
        <li v-for="p in shown" :key="p.id">
          <PassageCard :passage="p" :can-assign="isTeacher" :list="layout === 'list'" />
        </li>
      </ul>
      <p class="small muted" aria-live="polite">{{ shown.length }} of {{ passages.length }} passages. Source: GET /api/passages.</p>
    </StateBlock>
  </div>
</template>

<style scoped>
.tools { display: flex; gap: 8px; flex-wrap: wrap; }
.search { position: relative; display: flex; align-items: center; }
.search svg { position: absolute; left: 12px; color: var(--muted); pointer-events: none; }
.search .input { padding-left: 38px; width: 260px; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--r-sm); overflow: hidden; background: var(--surface); }
.seg button { min-width: 44px; min-height: 44px; border: 0; background: transparent; cursor: pointer; display: grid; place-items: center; color: var(--muted); }
.seg button[aria-pressed="true"] { background: var(--primary-soft); color: var(--primary); }
.grid { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.grid.grid { grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); }
.grid.list { grid-template-columns: minmax(0, 1fr); }
@media (max-width: 520px) { .search, .search .input { width: 100%; } .tools { width: 100%; } .search { flex: 1; } }
</style>
