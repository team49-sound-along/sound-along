<script setup>
// "By reader" view for one class (only mounted when the school switched on anonymous reader codes for it). A reader is a random code from one
// device, not a person. Each reader sees only their own history here: no ranking, no comparison, no grades.
import { computed, reactive, watch } from "vue";
import StateBlock from "./StateBlock.vue";
import LineChart from "./LineChart.vue";
import ColumnChart from "./ColumnChart.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import { readerColumns, readerPoints } from "../readAloudView.js";
import { readerLabel } from "../readerCode.js";

const props = defineProps({ classId: { type: String, required: true }, className: { type: String, required: true }, passageId: { type: String, default: "" } });
const pick = reactive({ code: "" });
const { data, loading, error, reload } = useResource(() => api.readAloudReaders({ classId: props.classId, code: pick.code, passageId: props.passageId }));
watch([() => props.classId, () => props.passageId, () => pick.code], reload);
const selected = computed(() => data.value?.selected ?? null);
</script>

<template>
  <section class="stack" aria-labelledby="rr-h" data-testid="ra-readers">
    <div>
      <h4 id="rr-h">Progress by reader: {{ className }}</h4>
      <p class="small muted">Each code is one device, not a name. A shared classroom device counts as one reader. Codes are listed in alphabetical order, never by results.</p>
    </div>
    <StateBlock :loading="loading && !data" :error="error" loading-label="Loading readers" @retry="reload">
      <template v-if="data">
        <p v-if="!data.enabled" class="notice" role="note">Progress by reader is off for this class.</p>
        <p v-else-if="!data.enough" class="notice" role="note" data-testid="ra-readers-few">Not enough readers yet. Reader progress appears once at least 3 different reader codes have read aloud in this class.</p>
        <template v-else>
          <div class="field">
            <label for="rr-code">Reader</label>
            <select id="rr-code" v-model="pick.code" class="input">
              <option value="">Choose a reader</option>
              <option v-for="r in data.readers" :key="r.code" :value="r.code">{{ readerLabel(r.code) }} ({{ r.sessions }} {{ r.sessions === 1 ? "session" : "sessions" }})</option>
            </select>
          </div>
          <p v-if="!selected" class="muted">Choose a reader to see their own progress.</p>
          <template v-else>
            <p class="notice ok" role="note" data-testid="ra-reader-summary"><strong>{{ readerLabel(selected.code) }}:</strong> {{ selected.summary }}</p>
            <LineChart title="Share of the passage read, by session" :points="readerPoints(selected.sessions)" :max="100" column="Passage read" />
            <ColumnChart title="Skipped and different words, by session" :columns="readerColumns(selected.sessions)" a-label="Skipped words" b-label="Words heard differently" />
            <div>
              <h4>Words this reader repeatedly misses</h4>
              <ul v-if="selected.words.length"><li v-for="w in selected.words" :key="w.word">{{ w.word }}: missed in {{ w.missed }} sessions</li></ul>
              <p v-else class="muted">No word has been missed more than once.</p>
            </div>
          </template>
        </template>
      </template>
    </StateBlock>
  </section>
</template>

<style scoped>
.stack { display: grid; gap: var(--s2); border-top: 1px solid var(--border); padding-top: var(--s2); }
h4 { font-size: 16px; margin: 0; }
ul { margin: 6px 0 0; padding-left: 20px; display: grid; gap: 4px; }
</style>
