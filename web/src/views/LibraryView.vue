<script setup>
import { computed, ref } from "vue";
import Icon from "../components/Icon.vue";
import StateBlock from "../components/StateBlock.vue";
import PassageCard from "../components/PassageCard.vue";
import { passageIndex } from "../api.js";
import { useResource } from "../useResource.js";
import { LANGUAGE_FILTERS, VOICE_FILTERS, filterLibrary } from "../libraryFilters.js";
import { groupVariants } from "../voices.js";
import { groupSeries } from "../series.js";
import { role } from "../session.js";

const { data, loading, error, reload } = useResource(passageIndex);
const query = ref("");
const voice = ref("any");
const language = ref("all");
const layout = ref("grid");
const passages = computed(() => groupSeries(groupVariants(data.value ?? [])));
const shown = computed(() => filterLibrary(passages.value, { query: query.value, voice: isTeacher.value ? voice.value : "any", language: language.value }));
const filtering = computed(() => Boolean(query.value.trim()) || (isTeacher.value && voice.value !== "any") || language.value !== "all");
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
        <a class="btn primary" href="#/generate">Create a passage</a>
        <div class="search">
          <Icon name="search" :size="18" />
          <label class="sr-only" for="q">Search passages by title</label>
          <input id="q" v-model="query" class="input" type="search" placeholder="Search passages" autocomplete="off" />
        </div>
        <div v-if="isTeacher" class="pick">
          <label class="sr-only" for="voice">Filter by voice</label>
          <select id="voice" v-model="voice" class="input">
            <option v-for="o in VOICE_FILTERS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>
        <div class="pick">
          <label class="sr-only" for="lang">Filter by language</label>
          <select id="lang" v-model="language" class="input">
            <option v-for="o in LANGUAGE_FILTERS" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
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
      empty-text="Create your first passage from any text."
      @retry="reload"
    >
      <p v-if="!shown.length" class="card muted" role="status"><template v-if="query.trim()">No passages match &ldquo;{{ query.trim() }}&rdquo; with these filters.</template><template v-else-if="filtering">No passages match these filters.</template><template v-else>No passages to show.</template></p>
      <ul v-else class="grid" :class="layout" aria-label="Passages">
        <li v-for="p in shown" :key="p.id">
          <PassageCard :passage="p" :can-assign="isTeacher" :list="layout === 'list'" />
        </li>
      </ul>
      <p class="small muted" aria-live="polite">{{ shown.length }} of {{ passages.length }} passages</p>
    </StateBlock>
  </div>
</template>

<style scoped>
.tools { display: flex; gap: 8px; flex-wrap: wrap; max-width: 100%; }
.search { position: relative; display: flex; align-items: center; }
.search svg { position: absolute; left: 12px; color: var(--muted); pointer-events: none; }
.search .input { padding-left: 38px; width: 240px; }
.pick .input { width: auto; min-width: 150px; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--r-sm); overflow: hidden; background: var(--surface); }
.seg button { min-width: 44px; min-height: 44px; border: 0; background: transparent; cursor: pointer; display: grid; place-items: center; color: var(--muted); }
.seg button[aria-pressed="true"] { background: var(--primary-soft); color: var(--primary); }
.grid { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s2); }
.grid.grid { grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr)); }
.grid.list { grid-template-columns: minmax(0, 1fr); }
@media (max-width: 520px) {
  .tools { width: 100%; }
  .search { flex: 1 1 100%; }
  .search, .search .input { width: 100%; }
  .pick { flex: 1 1 0; min-width: 0; }
  .pick .input { width: 100%; min-width: 0; }
}
</style>
