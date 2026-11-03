<script setup>
import { computed } from "vue";
import Icon from "./Icon.vue";
import { comparisonRows, isSmallSample, meanRows } from "../blind.js";
import { formatCount, formatRating } from "../format.js";

const props = defineProps({ summary: { type: Object, default: null } });
const comparisons = computed(() => comparisonRows(props.summary));
const means = computed(() => meanRows(props.summary));
const hasData = computed(() => Boolean(props.summary) && props.summary.ratings > 0);
</script>

<template>
  <section class="card stack" aria-labelledby="blind-h">
    <div>
      <h3 id="blind-h">Blind listening test</h3>
      <p class="small muted">Listeners rate two unlabelled readings of the same text. Source: ratings recorded by this server.</p>
    </div>
    <div v-if="!hasData" class="empty">
      <strong>No ratings yet.</strong>
      <p class="muted">Open the <a href="#/listening">Listening test</a> and rate a few clips.</p>
    </div>
    <template v-else>
      <dl class="totals">
        <div><dt>Raters</dt><dd class="num">{{ formatCount(summary.raters) }}</dd></div>
        <div><dt>Ratings</dt><dd class="num">{{ formatCount(summary.ratings) }}</dd></div>
      </dl>
      <div v-if="isSmallSample(summary)" class="notice warn caveat" role="note">
        <Icon name="alert" />
        <p class="small"><strong>Small sample.</strong> With this few ratings the results are not statistically meaningful. Treat them as a first impression, not proof.</p>
      </div>

      <div v-if="comparisons.length">
        <h4>Which reading was preferred</h4>
        <div class="table-wrap">
          <table class="data stacked">
            <thead>
              <tr><th scope="col">Comparison</th><th scope="col" class="num">Ratings (n)</th><th scope="col" class="num">Preferred AI voice</th><th scope="col" class="num">Preferred other</th><th scope="col" class="num">No difference</th></tr>
            </thead>
            <tbody>
              <tr v-for="c in comparisons" :key="c.key">
                <th scope="row" class="rowhead">{{ c.label }}</th>
                <td class="num" data-label="Ratings (n)">{{ formatCount(c.n) }}</td>
                <td class="num" data-label="Preferred AI voice">{{ formatCount(c.preferredAi) }}</td>
                <td class="num" data-label="Preferred other">{{ formatCount(c.preferredOther) }}</td>
                <td class="num" data-label="No difference">{{ formatCount(c.tie) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h4>Mean rating by narrator (1 robotic to 5 like a person)</h4>
        <div class="table-wrap">
          <table class="data stacked">
            <thead><tr><th scope="col">Narrator</th><th scope="col" class="num">Mean rating</th></tr></thead>
            <tbody>
              <tr v-for="m in means" :key="m.key">
                <th scope="row" class="rowhead">{{ m.label }}</th>
                <td class="num" data-label="Mean rating">{{ formatRating(m.value) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
.stack { display: grid; gap: var(--s2); }
h4 { font-size: 14px; margin-bottom: 8px; }
.empty { display: grid; gap: 4px; padding: var(--s2); border: 1px dashed var(--border); border-radius: var(--r-sm); background: var(--surface-2); }
.totals { display: flex; flex-wrap: wrap; gap: var(--s4); margin: 0; }
.totals dt { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; color: var(--muted); }
.totals dd { margin: 0; font-size: 28px; font-weight: 700; }
.caveat { align-items: flex-start; }
.caveat svg { flex: none; margin-top: 2px; }
.rowhead { text-align: left; font-weight: 600; }
table.data tbody th.rowhead { padding: 12px var(--s2); border-bottom: 1px solid var(--border); background: transparent; text-transform: none; letter-spacing: 0; font-size: 15px; color: var(--text); white-space: normal; }
@media (max-width: 640px) {
  .stacked thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  .stacked, .stacked tbody, .stacked tr, .stacked td, .stacked th.rowhead { display: block; width: 100%; }
  .stacked tr { border-bottom: 1px solid var(--border); padding: 8px 0; }
  .stacked tr:last-child { border-bottom: 0; }
  .stacked td, table.data tbody th.rowhead { border: 0; padding: 4px var(--s2); }
  .stacked td { display: flex; justify-content: space-between; gap: var(--s2); text-align: right; }
  .stacked td::before { content: attr(data-label); font-weight: 600; text-align: left; color: var(--muted); }
}
</style>
