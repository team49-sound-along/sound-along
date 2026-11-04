<script setup>
import { computed } from "vue";
import StateBlock from "../components/StateBlock.vue";
import KpiCard from "../components/KpiCard.vue";
import CostChart from "../components/CostChart.vue";
import BlindRating from "../components/BlindRating.vue";
import Icon from "../components/Icon.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import { formatCount, formatMinutes, formatMos, formatMs, formatPercent, formatRtf, formatShare, percentOf } from "../format.js";

const { data, loading, error, reload } = useResource(api.insights);

const rowsFor = (c) => [
  { key: "neural", label: "Amazon Polly Neural", value: c?.pollyNeuralUsd },
  { key: "standard", label: "Amazon Polly Standard", value: c?.pollyStandardUsd },
  { key: "lambda", label: "Estimated cost, our approach (self-hosted)", value: c?.estimatedLambdaUsd, estimated: true },
];
const current = computed(() => rowsFor(data.value?.cost));
const projected = computed(() => rowsFor(data.value?.cost?.projectedCatalog));
const adoption = computed(() => data.value?.adoption ?? {});
const saShare = computed(() => percentOf(adoption.value.assignmentsWithSoundAlong, adoption.value.assignmentsTotal));
const projChars = computed(() => data.value?.cost?.projectedCatalog?.characters);
const agreement = computed(() => data.value?.quality?.timingAgreement ?? null);
const agreementSource = computed(() => {
  const a = agreement.value;
  if (!a) return "Not measured yet. Run scripts/build_samples.py.";
  return `Independent speech check vs our timing on ${formatCount(a.wordsChecked)} words: p95 ${formatMs(a.p95ErrorMs)}, ${formatShare(a.within100ms)} within 100 ms, word error ${formatPercent(a.wer * 100)}. Agreement between two systems, not ground truth.`;
});
const naturalness = computed(() => {
  const scores = data.value?.quality?.naturalness?.scores ?? {};
  const label = {
    ai_voice_park: "AI voice, Park Caretaker",
    readworks_human_park: "ReadWorks human recording, Park Caretaker",
    ai_voice_pride: "AI voice, Pride and Prejudice",
    readworks_current_polly_pride: "ReadWorks current audio (Polly), Pride and Prejudice",
  };
  return Object.entries(scores).map(([key, s]) => ({ key, label: label[key] ?? key, mos: s.meanMos }));
});
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>Insights</h2>
        <p>Catalog quality, generation cost and classroom adoption. Each figure notes where it comes from. Missing values show as an em dash.</p>
      </div>
    </div>

    <StateBlock :loading="loading" :error="error" loading-label="Loading insights" @retry="reload">
      <template v-if="data">
        <section aria-labelledby="kpi-h" class="stack">
          <h3 id="kpi-h" class="sr-only">Key metrics</h3>
          <div class="kpis">
            <KpiCard label="Passages" :value="formatCount(data.catalog?.passages)" source="Measured: count of published passages" />
            <KpiCard label="Audio minutes" :value="formatMinutes(data.catalog?.audioMinutes)" source="Measured: total generated audio length" />
            <KpiCard label="Timing vs independent check" :value="formatMs(agreement?.medianErrorMs)" :source="agreementSource" emphasis />
            <KpiCard label="Words mapped" :value="formatPercent(data.quality?.alignedPercent)" :source="`Voice word timings mapped to displayed words (${formatCount(data.quality?.unalignedWords)} not exact). This is not a sync measure.`" />
            <KpiCard label="Avg real-time factor" :value="formatRtf(data.speed?.avgRealTimeFactor)" source="Measured while generating on a development computer; speed in production will differ" />
          </div>
        </section>

        <section v-if="naturalness.length" class="card stack" aria-labelledby="nat-h">
          <div>
            <h3 id="nat-h">Predicted narration naturalness</h3>
            <p class="small muted">{{ data.quality.naturalness.method }}</p>
          </div>
          <div class="table-wrap">
            <table class="data">
              <thead><tr><th scope="col">Audio</th><th scope="col" class="num">Predicted MOS</th></tr></thead>
              <tbody>
                <tr v-for="row in naturalness" :key="row.key"><td>{{ row.label }}</td><td class="num">{{ formatMos(row.mos) }}</td></tr>
              </tbody>
            </table>
          </div>
          <p class="small muted">Scores run from 1 (poor) to 5 (excellent).</p>
        </section>

        <BlindRating :summary="data.quality?.blindRating ?? null" />

        <section class="card stack" aria-labelledby="cost-h">
          <div>
            <h3 id="cost-h">Cost to generate narration</h3>
            <p class="small muted">Lower is better. Each chart has its own scale.</p>
          </div>
          <div class="notice warn caveat" role="note">
            <Icon name="alert" />
            <div>
              <strong>Estimate, not a measured bill.</strong>
              <p class="small">{{ data.cost?.basis || "—" }}</p>
              <p class="small muted">Estimates from the passages generated so far.</p>
            </div>
          </div>
          <div class="charts">
            <CostChart title="Current catalog" :subtitle="`${formatCount(data.catalog?.characters)} characters`" :rows="current" />
            <CostChart title="Projected ReadWorks catalog" :subtitle="`${formatCount(projChars)} characters (projection)`" :rows="projected" />
          </div>
        </section>

        <section class="card stack" aria-labelledby="adopt-h">
          <div>
            <h3 id="adopt-h">Classroom adoption</h3>
            <p class="small muted">Based on reading activity (plays, word taps, completions) and assignments recorded in this app.</p>
          </div>
          <dl class="adopt">
            <div><dt>Plays</dt><dd class="num">{{ formatCount(adoption.plays) }}</dd></div>
            <div><dt>Word taps</dt><dd class="num">{{ formatCount(adoption.wordTaps) }}</dd></div>
            <div><dt>Completions</dt><dd class="num">{{ formatCount(adoption.completions) }}</dd></div>
            <div>
              <dt>Assignments with Sound Along</dt>
              <dd class="num">{{ formatPercent(saShare, 0) }}</dd>
              <dd class="small muted">{{ formatCount(adoption.assignmentsWithSoundAlong) }} of {{ formatCount(adoption.assignmentsTotal) }} assignments</dd>
            </div>
          </dl>
        </section>
      </template>
    </StateBlock>
  </div>
</template>

<style scoped>
.stack { display: grid; gap: var(--s2); }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--s2); }
.charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr)); gap: var(--s4); }
.caveat { align-items: flex-start; }
.caveat svg { flex: none; margin-top: 2px; }
.adopt { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: var(--s3); margin: 0; }
.adopt dt { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; color: var(--muted); }
.adopt dd { margin: 0; font-size: 28px; font-weight: 700; }
.adopt dd.small { font-size: 14px; font-weight: 400; }
</style>
