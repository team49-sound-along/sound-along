<script setup>
import { computed } from "vue";
import ChartTable from "./ChartTable.vue";
import { barRows } from "../chartData.js";

// rows: [{ key, label, value|null, text, note }]. A row with no value shows `note` instead of a bar ("Not enough sessions yet").
// The number is always written beside the bar, so nothing depends on colour or length alone.
const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: "" },
  rows: { type: Array, required: true },
  max: { type: Number, default: undefined },
  column: { type: String, default: "Value" },
  hideTitle: Boolean, // the title stays for screen readers when a heading on the page already asks the question
  showTable: { type: Boolean, default: true }, // the "Show as a table" alternative; the main teacher view turns it off (numbers are written beside the bars)
});

const W = 560, ROW = 46, PAD_L = 8, PAD_R = 150, BAR_H = 22;
const bars = computed(() => barRows(props.rows, { max: props.max }).map((r, n) => ({ ...r, y: n * ROW + 22, width: r.share === null ? 0 : Math.max(3, r.share * (W - PAD_L - PAD_R)) })));
const shown = (b) => (b.value == null ? b.note : b.text);
const label = (b) => `${b.label}: ${shown(b)}`;
const summary = computed(() => `${props.title}: ${bars.value.map(label).join("; ")}`);
const table = computed(() => bars.value.map((b) => [b.label, shown(b)]));
</script>

<template>
  <figure class="chart">
    <figcaption :class="{ 'sr-only': hideTitle }"><strong>{{ title }}</strong><span v-if="subtitle" class="small muted">{{ subtitle }}</span></figcaption>
    <svg :viewBox="`0 0 ${W} ${rows.length * ROW + 8}`" role="group" :aria-label="summary" preserveAspectRatio="xMinYMin meet">
      <g v-for="b in bars" :key="b.key">
        <text :x="PAD_L" :y="b.y - 7" class="lbl">{{ b.label }}</text>
        <rect :x="PAD_L" :y="b.y" :width="W - PAD_L - PAD_R" :height="BAR_H" rx="6" class="track" />
        <rect v-if="b.share !== null" :x="PAD_L" :y="b.y" :width="b.width" :height="BAR_H" rx="6" class="bar" tabindex="0" role="img" :aria-label="label(b)"><title>{{ label(b) }}</title></rect>
        <text :x="W - PAD_R + 10" :y="b.y + 16" class="val">{{ shown(b) }}</text>
      </g>
    </svg>
    <ChartTable v-if="showTable" :caption="title" :columns="['Item', column]" :rows="table" />
  </figure>
</template>

<style scoped>
.chart { margin: 0; display: grid; gap: 8px; }
figcaption { display: grid; gap: 2px; }
svg { width: 100%; height: auto; display: block; }
.lbl { font: 600 13px var(--ui); fill: var(--text); }
.val { font: 700 13px var(--ui); fill: var(--text); font-variant-numeric: tabular-nums; }
.track { fill: var(--surface-2); stroke: var(--border); }
.bar { fill: var(--primary); }
.bar:focus { outline: 3px solid var(--text); outline-offset: 2px; }
</style>
