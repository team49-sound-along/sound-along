<script setup>
// Teacher-only "Reading aloud" section of Insights, in the order a teacher asks: are they finishing, which words are hard, what do I do next,
// who needs a hand (only when reader codes are on). Raw numbers sit behind "Show the numbers" and the school's switches behind
// "Settings and privacy", at the bottom. Anonymous, class-level counts only: no names, no recordings, no transcripts.
import { computed, reactive, ref, watch } from "vue";
import StateBlock from "./StateBlock.vue";
import LineChart from "./LineChart.vue";
import HBarChart from "./HBarChart.vue";
import ReadAloudControls from "./ReadAloudControls.vue";
import ReadAloudReaders from "./ReadAloudReaders.vue";
import ReadAloudStatus from "./ReadAloudStatus.vue";
import ReadAloudSteps from "./ReadAloudSteps.vue";
import PassageHeatMap from "./PassageHeatMap.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import { classRateRows, hardestRows, hasTrend, leftOutNote, numbersList, trendPoints, weekPoints, wordRows } from "../readAloudView.js";
import { defaultPassage, headline, suggestions } from "../readAloudStory.js";

const filters = reactive({ passageId: "", classId: "" });
const { data, loading, error, reload } = useResource(() => api.readAloudInsights({ passageId: filters.passageId, classId: filters.classId }));
const settingsState = useResource(() => api.readAloudSettings());
const changed = ref(null);
const settings = computed(() => changed.value ?? settingsState.data.value);
watch(filters, reload);
// Open on the passage with the most reads, and move on when the chosen class has not read the chosen passage.
watch(data, (d) => {
  if (!d || d.passages.some((p) => p.id === filters.passageId)) return;
  const next = defaultPassage(d.passages);
  if (next !== filters.passageId) filters.passageId = next;
});

const nothingYet = computed(() => data.value && data.value.passages.length === 0 && data.value.totals.sessions === 0 && data.value.hiddenSessions === 0);
const className = computed(() => settings.value?.classes.find((c) => c.id === filters.classId)?.name ?? "");
const passageTitle = computed(() => data.value?.passages.find((p) => p.id === filters.passageId)?.title ?? "");
const scope = computed(() => [passageTitle.value || "All passages", className.value || "all classes"].join(", "));
const enough = computed(() => data.value?.words.state === "ok");
const story = computed(() => (data.value ? headline({ who: className.value, title: passageTitle.value, totals: data.value.totals, words: data.value.words }) : ""));
const steps = computed(() => (data.value ? suggestions({ totals: data.value.totals, words: data.value.words, heat: data.value.passage }) : []));
const trend = computed(() => (data.value && hasTrend(data.value.weeks) ? trendPoints(data.value.weeks) : null));
const numbers = computed(() => numbersList(data.value?.totals));
const leftOut = computed(() => (data.value ? leftOutNote(data.value.hiddenSessions, data.value.minSessions) : ""));
const readerClass = computed(() => settings.value?.classes.find((c) => c.id === filters.classId && c.readers) ?? null);
const readsSoFar = computed(() => data.value?.hiddenSessions ?? 0);
</script>

<template>
  <section class="card stack" aria-labelledby="ra-h" data-testid="ra-section">
    <div>
      <h3 id="ra-h">Reading aloud</h3>
      <p class="small muted">From students who read aloud with the mic. Word counts only: no names, no recordings.</p>
    </div>

    <StateBlock :loading="loading && !data" :error="error" loading-label="Loading reading results" @retry="reload">
      <template v-if="data">
        <div class="filters">
          <div class="field">
            <label for="ra-passage">Passage</label>
            <select id="ra-passage" v-model="filters.passageId" class="input">
              <option v-if="!data.passages.length" value="">No passage yet</option>
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
          <p class="muted">When students tap <em>Read aloud with the mic</em> in a class where sharing is on, you will see here how they are doing and which words are hard.</p>
        </div>

        <div v-else class="stack" :class="{ busy: loading }">
          <p class="headline" data-testid="ra-headline" aria-live="polite">{{ story }}</p>

          <template v-if="enough">
            <section class="stack" aria-labelledby="q1">
              <h4 id="q1">Did they finish?</h4>
              <ReadAloudStatus :totals="data.totals" :classes="data.classes" :by-class="!filters.classId && data.classes.length > 1" />
            </section>

            <section v-if="data.passage" class="stack" aria-labelledby="q2">
              <h4 id="q2">Which words are hard?</h4>
              <PassageHeatMap :passage="data.passage" :words="data.words.items" />
            </section>

            <section class="stack" aria-labelledby="q3" data-testid="ra-top-words">
              <h4 id="q3">Which 5 words were missed most?</h4>
              <HBarChart title="Words missed most" :rows="hardestRows(data.words.items)" :max="1" column="Readers who missed it" :show-table="false" hide-title />
            </section>

            <section v-if="steps.length" class="stack" aria-labelledby="q5">
              <h4 id="q5">What to do next</h4>
              <ReadAloudSteps :cards="steps" />
            </section>
          </template>

          <div v-else class="empty" data-testid="ra-thin">
            <strong>Not enough readers yet.</strong>
            <p class="muted">Once 3 students have read this passage aloud you will see which words are hard.<span v-if="readsSoFar > 0"> So far {{ readsSoFar }} {{ readsSoFar === 1 ? "student has" : "students have" }}.</span></p>
            <p class="muted">To get there: open the passage, then tap <em>Read aloud with the mic</em>. Ask a few students to try it.</p>
          </div>

          <ReadAloudReaders v-if="readerClass" :class-id="readerClass.id" :class-name="readerClass.name" :passage-id="filters.passageId" />
          <p v-else-if="settings?.readersAvailable && filters.classId" class="small muted">Progress by reader is off for this class. You can turn it on under Settings and privacy.</p>

          <p class="small muted" data-testid="ra-min-note">Shown only for groups of {{ data.minSessions }} or more readers, so one child never stands out.<span v-if="leftOut">{{ ` ${leftOut}` }}</span></p>

          <details class="more" data-testid="ra-numbers">
            <summary>Show the numbers</summary>
            <div class="stack inner">
              <dl class="nums">
                <div v-for="n in numbers" :key="n.label"><dt>{{ n.label }}</dt><dd class="num">{{ n.value }}</dd><dd class="small muted">{{ n.note }}</dd></div>
              </dl>
              <LineChart v-if="trend" title="Are they improving? Share who finished, week by week" :points="trend" :max="100" column="Finished" />
              <p v-else class="small muted">A progress line appears here once students have read in two different weeks.</p>
              <LineChart title="Reads over the last 8 weeks" :subtitle="scope" :points="weekPoints(data.weeks)" area column="Reads" />
              <div v-if="!filters.classId" class="charts">
                <HBarChart title="Finished, by class" :rows="classRateRows(data.classes, 'finishRate', 'finished')" :max="1" column="Finished" />
                <HBarChart title="Went back to re-read, by class" :rows="classRateRows(data.classes, 'retryRate', 'went back')" :max="1" column="Went back" />
              </div>
              <HBarChart v-if="enough" title="Words students stumbled on" subtitle="Missed or heard as a different word, out of all reads" :rows="wordRows(data.words.items)" :max="1" column="Reads" />
            </div>
          </details>
        </div>
      </template>
    </StateBlock>

    <details class="more" data-testid="ra-settings">
      <summary>Settings and privacy</summary>
      <div class="inner">
        <StateBlock :loading="settingsState.loading.value" :error="settingsState.error.value" loading-label="Loading switches" @retry="settingsState.reload">
          <ReadAloudControls v-if="settings" :view="settings" @change="changed = $event; reload()" />
        </StateBlock>
      </div>
    </details>
  </section>
</template>

<style scoped>
.stack { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--s2); }
.filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: var(--s2); }
.charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr)); gap: var(--s4); }
.empty { display: grid; gap: 4px; padding: var(--s3); border: 1px dashed var(--border); border-radius: var(--r); }
.headline { font-size: 22px; line-height: 1.35; font-weight: 700; margin: 0; max-width: 40ch; }
.busy { opacity: 0.6; }
h4 { font-size: 18px; margin: 0; }
.more { border-top: 1px solid var(--border); padding-top: var(--s1); }
.more > summary { cursor: pointer; font-weight: 600; min-height: 44px; display: flex; align-items: center; }
.inner { padding-top: var(--s2); display: grid; gap: var(--s2); }
.nums { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--s2); margin: 0; }
.nums dt { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; color: var(--muted); }
.nums dd { margin: 0; }
.nums dd.num { font-size: 28px; font-weight: 700; }
@media (prefers-reduced-motion: no-preference) { .busy { transition: opacity 0.2s; } }
</style>
