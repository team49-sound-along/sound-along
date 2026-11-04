<script setup>
import { computed, ref, watch } from "vue";
import StateBlock from "../components/StateBlock.vue";
import PronunciationForm from "../components/PronunciationForm.vue";
import PronunciationsTable from "../components/PronunciationsTable.vue";
import { api } from "../api.js";
import { route } from "../router.js";
import { useResource } from "../useResource.js";
import { normalizeWord, removePronunciation, upsertPronunciation } from "../pronunciations.js";

const { data, loading, error, reload } = useResource(() => api.pronunciations());
const items = ref([]);
watch(data, (d) => { if (d) items.value = d; });

const preset = computed(() => normalizeWord(route.value.query.word || ""));
const form = ref(null);
const known = computed(() => items.value.map((p) => p.word));
const busy = ref(false);
const formError = ref("");
const rowError = ref("");
const rowErrorWord = ref("");
const busyWord = ref("");
const flash = ref("");
const actionError = ref("");

async function add(word, respelling) {
  busy.value = true;
  formError.value = "";
  try {
    const saved = await api.savePronunciation(word, respelling);
    items.value = upsertPronunciation(items.value, saved);
    flash.value = `Saved "${saved.word}". New and regenerated passages will use it.`;
    form.value?.clear();
  } catch (e) {
    formError.value = e.message;
  } finally {
    busy.value = false;
  }
}

async function saveRow(word, respelling, done) {
  busyWord.value = word;
  rowError.value = "";
  try {
    items.value = upsertPronunciation(items.value, await api.savePronunciation(word, respelling));
    flash.value = `Updated "${word}".`;
    done();
  } catch (e) {
    rowError.value = e.message;
    rowErrorWord.value = word;
  } finally {
    busyWord.value = "";
  }
}

async function remove(word) {
  actionError.value = "";
  try {
    await api.deletePronunciation(word);
    items.value = removePronunciation(items.value, word);
    flash.value = `Deleted "${word}".`;
  } catch (e) {
    actionError.value = `Could not delete "${word}". ${e.message}`;
  }
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>Pronunciations</h2>
        <p>Teach the voice how to say names and unusual words. Fixes apply to passages generated or regenerated from now on.</p>
      </div>
    </div>
    <PronunciationForm ref="form" :preset-word="preset" :known="known" :busy="busy" :error="formError" @save="add" />
    <p class="sr-only" role="status" aria-live="polite">{{ flash }}</p>
    <p v-if="flash" class="notice ok">{{ flash }}</p>
    <p v-if="actionError" class="notice error" role="alert">{{ actionError }}</p>
    <StateBlock :loading="loading" :error="error" :empty="!loading && !error && !items.length" empty-title="No pronunciation fixes yet" empty-text="Add one above, or open Pronunciation review to see words that may be mispronounced." loading-label="Loading pronunciations" @retry="reload">
      <section aria-labelledby="pl-h" class="stack">
        <h3 id="pl-h">Current fixes ({{ items.length }})</h3>
        <div class="card flush">
          <PronunciationsTable :items="items" :busy-word="busyWord" :error="rowError" :error-word="rowErrorWord" @save="saveRow" @remove="remove" />
        </div>
      </section>
    </StateBlock>
  </div>
</template>

<style scoped>
.stack { display: grid; gap: var(--s2); }
</style>
