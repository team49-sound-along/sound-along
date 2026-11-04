<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
import Icon from "../components/Icon.vue";
import StateBlock from "../components/StateBlock.vue";
import PassageCard from "../components/PassageCard.vue";
import { api, passageIndex } from "../api.js";
import { useResource } from "../useResource.js";
import { LANGUAGE_FILTERS, VOICE_FILTERS, filterLibrary } from "../libraryFilters.js";
import { groupVariants } from "../voices.js";
import { role } from "../session.js";

const { data, loading, error, reload } = useResource(passageIndex);
const query = ref("");
const voice = ref("any");
const language = ref("all");
const layout = ref("grid");
const passages = computed(() => groupVariants(data.value ?? []));
const shown = computed(() => filterLibrary(passages.value, { query: query.value, voice: isTeacher.value ? voice.value : "any", language: language.value }));
const filtering = computed(() => Boolean(query.value.trim()) || (isTeacher.value && voice.value !== "any") || language.value !== "all");
const isTeacher = computed(() => role.value === "teacher");

// A teacher also sees what is still being made (the audio and its translation). It is never offered for reading until it is complete.
const pending = ref([]);
async function checkPending() {
  if (!isTeacher.value) {
    pending.value = [];
    return;
  }
  try {
    const next = groupVariants(await api.pendingPassages());
    const had = pending.value.length;
    pending.value = next;
    if (had && !next.length) reload(); // it just became ready
  } catch {
    /* the list of finished passages still works without this */
  }
}
// Checks every 5 s while something is being made, otherwise every 30 s, and not at all while the tab is hidden (it checks again as soon as it is shown).
let pendingTimer = 0;
async function loop() {
  if (!document.hidden) await checkPending();
  pendingTimer = setTimeout(loop, pending.value.length ? 5000 : 30000);
}
const onVisible = () => { if (!document.hidden) { clearTimeout(pendingTimer); loop(); } };
document.addEventListener("visibilitychange", onVisible);
loop();
onBeforeUnmount(() => { clearTimeout(pendingTimer); document.removeEventListener("visibilitychange", onVisible); });
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>Library</h2>
        <p>Every passage is read aloud and each word lights up as you listen. Tap any word to hear it again.</p>
      </div>
      <div class="tools">
        <a v-if="isTeacher" class="btn primary" href="#/generate">Create a passage</a>
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

    <section v-if="isTeacher && pending.length" class="card pending" aria-labelledby="pend-h" role="status">
      <h3 id="pend-h">Being created</h3>
      <ul>
        <li v-for="p in pending" :key="p.id"><strong>{{ p.title }}</strong> <span class="muted small">being made</span></li>
      </ul>
      <p class="small muted">A passage appears in the Library when every part and its translation are ready. This list updates by itself.</p>
    </section>
    <StateBlock
      :loading="loading"
      :error="error"
      :empty="!passages.length"
      loading-label="Loading passages"
      empty-title="No passages yet"
      :empty-text="isTeacher ? 'Create your first passage from any text.' : 'Passages appear here once your teacher adds them.'"
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
.pending { display: grid; gap: var(--s1); }
.pending ul { margin: 0; padding-left: 20px; display: grid; gap: 4px; }
.tools { display: flex; gap: 8px; flex-wrap: wrap; max-width: 100%; }
.search { position: relative; display: flex; align-items: center; }
.search svg { position: absolute; left: 12px; color: var(--muted); pointer-events: none; }
.search .input { padding-left: 38px; width: 240px; }
.pick .input { width: 180px; }
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
  .pick { flex: 1 1 calc(50% - 8px); min-width: 0; }
  .pick .input { width: 100%; min-width: 0; }
  .seg { margin-left: auto; }
}
</style>
