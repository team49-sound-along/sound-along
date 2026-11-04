<script setup>
// Teacher-only "Reading aloud" section of Insights: anonymous, class-level numbers from the end-of-session word counts. Per class, per
// passage or across the school; a "by reader" view appears only when the school switched on anonymous reader codes for a class.
import { computed, reactive, ref, watch } from "vue";
import StateBlock from "./StateBlock.vue";
import KpiCard from "./KpiCard.vue";
import LineChart from "./LineChart.vue";
import HBarChart from "./HBarChart.vue";
import ReadAloudControls from "./ReadAloudControls.vue";
import ReadAloudReaders from "./ReadAloudReaders.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import { classRateRows, rateNote, tiles, weekPoints, wordRows, wordsMessage } from "../readAloudView.js";

const filters = reactive({ passageId: "", classId: "" });
const { data, loading, error, reload } = useResource(() => api.readAloudInsights({ passageId: filters.passageId, classId: filters.classId }));
const settingsState = useResource(() => api.readAloudSettings());
const changed = ref(null);
const settings = computed(() => changed.value ?? settingsState.data.value);
watch(filters, reload);

const shown = computed(() => tiles(data.value?.totals));
const nothingYet = computed(() => data.value && data.value.passages.length === 0 && data.value.totals.sessions === 0 && data.value.hiddenSessions === 0);
const message = computed(() => (data.value ? wordsMessage(data.value.words, data.value.hiddenSessions, data.value.minSessions) : ""));
const note = computed(() => (data.value ? rateNote(data.value.hiddenSessions, data.value.minSessions) : ""));
const words = computed(() => wordRows(data.value?.words.items));
const scope = computed(() => {
  const pass = data.value?.passages.find((p) => p.id === filters.passageId)?.title;
  const cls = settings.value?.classes.find((c) => c.id === filters.classId)?.name;
  return [pass ?? "All passages", cls ?? "all classes"].join(", ");
});
const readerClass = computed(() => settings.value?.classes.find((c) => c.id === filters.classId && c.readers) ?? null);
</script>

<template>
  <section class="card stack" aria-labelledby="ra-h" data-testid="ra-section">
    <div>
      <h3 id="ra-h">Reading aloud</h3>
      <p class="small muted">Anonymous word counts from students who read with the microphone. No names, no recordings and no transcripts.</p>
    </div>

    <StateBlock :loading="settingsState.loading.value" :error="settingsState.error.value" loading-label="Loading switches" @retry="settingsState.reload">
      <ReadAloudControls v-if="settings" :view="settings" @change="changed = $event; reload()" />
    </StateBlock>

    <StateBlock :loading="loading" :error="error" loading-label="Loading reading results" @retry="reload">
      <template v-if="data">
        <div class="filters">
          <div class="field">
            <label for="ra-passage">Passage</label>
            <select id="ra-passage" v-model="filters.passageId" class="input">
              <option value="">All passages</option>
              <option v-for="p in data.passages" :key="p.id" :value="p.id">{{ p.title }}</option>
            </select>
          </div>
          <div class="field">
            <label for="ra-class">Class</label>
            <select id="ra-class" v-model="filters.classId" class="input">
              <option value="">All classes</option>
              <option v-for="c in settings?.classes ?? []" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
        </div>

        <div v-if="nothingYet" class="empty" data-testid="ra-empty">
          <strong>No one has read aloud yet.</strong>
          <p class="muted">When students use <em>Read aloud with the mic</em> in a class where sharing is on, results appear here.</p>
        </div>

        <template v-else>
          <p class="small muted" data-testid="ra-scope">Showing: {{ scope }}</p>
          <div class="kpis">
            <KpiCard label="Sessions" :value="shown.sessions" source="Times a student read aloud" />
            <KpiCard label="Finish rate" :value="shown.finish" source="Sessions that reached the end of the passage" />
            <KpiCard label="Tried again" :value="shown.retry" source="Sessions where the student read a part again" />
          </div>
          <p class="notice small" role="note" data-testid="ra-min-note">To protect privacy, numbers and word lists are shown only for groups with at least {{ data.minSessions }} sessions ({{ data.minSessions }} different readers when reader codes are on). One student&rsquo;s reading is never shown on its own here.<span v-if="note"> {{ note }}</span></p>

          <LineChart title="Sessions over the last 8 weeks" :subtitle="scope" :points="weekPoints(data.weeks)" area column="Sessions" />

          <div v-if="!filters.classId" class="charts">
            <HBarChart title="Finish rate by class" :rows="classRateRows(data.classes, 'finishRate', 'finished')" :max="1" column="Finish rate" />
            <HBarChart title="Tried again, by class" :rows="classRateRows(data.classes, 'retryRate', 'tried again')" :max="1" column="Tried again" />
          </div>

          <div class="stack">
            <HBarChart v-if="data.words.state === 'ok'" title="Words students stumble on" subtitle="Skipped or heard as a different word, out of all counted sessions" :rows="words" :max="1" column="Sessions" />
            <div v-else>
              <h4>Words students stumble on</h4>
              <p class="notice" role="note" data-testid="ra-words-note">{{ message }}</p>
            </div>
          </div>

          <div v-if="data.steps.length" class="stack" data-testid="ra-steps">
            <h4>Suggested next steps</h4>
            <ul><li v-for="step in data.steps" :key="step">{{ step }}</li></ul>
          </div>
        </template>

        <ReadAloudReaders v-if="readerClass" :class-id="readerClass.id" :class-name="readerClass.name" :passage-id="filters.passageId" />
        <p v-else-if="settings?.readersAvailable && filters.classId" class="small muted">Progress by reader is off for this class. You can turn it on in the switches above.</p>
      </template>
    </StateBlock>
  </section>
</template>

<style scoped>
.stack { display: grid; gap: var(--s2); }
.filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: var(--s2); }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--s2); }
.charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr)); gap: var(--s4); }
.empty { display: grid; gap: 4px; padding: var(--s3); border: 1px dashed var(--border); border-radius: var(--r); }
h4 { font-size: 16px; margin: 0; }
ul { margin: 0; padding-left: 20px; display: grid; gap: 6px; }
</style>
