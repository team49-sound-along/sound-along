<script setup>
import { computed, useId } from "vue";
import ChartTable from "./ChartTable.vue";
import { columnBars } from "../chartData.js";

// columns: [{ label, a, b }]: two counts per column, drawn side by side. `a` is solid, `b` is hatched, and each column is named in text.
const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: "" },
  columns: { type: Array, required: true },
  aLabel: { type: String, required: true },
  bLabel: { type: String, required: true },
});

const uid = useId();
const W = 560, H = 190, LEFT = 30, TOP = 12, BOTTOM = 30;
const inner = H - TOP - BOTTOM;
const scale = computed(() => columnBars(props.columns.flatMap((c) => [c.a, c.b])));
const slot = computed(() => (W - LEFT - 8) / Math.max(1, props.columns.length));
const bw = computed(() => Math.min(26, slot.value / 2 - 4));
const cols = computed(() =>
  props.columns.map((c, i) => {
    const x = LEFT + i * slot.value + slot.value / 2;
    const [a, b] = scale.value.bars.slice(i * 2, i * 2 + 2);
    return { ...c, x, ha: a.share * inner, hb: b.share * inner, name: `${c.label}: ${props.aLabel} ${c.a}, ${props.bLabel} ${c.b}` };
  }),
);
const summary = computed(() => `${props.title}: ${cols.value.map((c) => c.name).join("; ")}`);
const table = computed(() => props.columns.map((c) => [c.label, c.a, c.b]));
</script>

<template>
  <figure class="chart">
    <figcaption><strong>{{ title }}</strong><span v-if="subtitle" class="small muted">{{ subtitle }}</span></figcaption>
    <svg :viewBox="`0 0 ${W} ${H}`" role="group" :aria-label="summary" preserveAspectRatio="xMinYMin meet">
      <defs>
        <pattern :id="`hatch-${uid}`" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--surface)" /><rect width="3" height="6" fill="var(--text)" /></pattern>
      </defs>
      <line :x1="LEFT" :x2="W - 8" :y1="TOP + inner" :y2="TOP + inner" class="axis" />
      <text :x="LEFT - 6" :y="TOP + 10" class="tick" text-anchor="end">{{ scale.max }}</text>
      <text :x="LEFT - 6" :y="TOP + inner" class="tick" text-anchor="end">0</text>
      <g v-for="(c, i) in cols" :key="i" tabindex="0" role="img" :aria-label="c.name" class="col">
        <title>{{ c.name }}</title>
        <rect :x="c.x - bw - 1" :y="TOP + inner - c.ha" :width="bw" :height="c.ha" class="a" />
        <rect :x="c.x + 1" :y="TOP + inner - c.hb" :width="bw" :height="c.hb" :fill="`url(#hatch-${uid})`" class="b" />
        <text :x="c.x" :y="H - 10" class="tick" text-anchor="middle">{{ c.label }}</text>
      </g>
    </svg>
    <p class="small muted legend"><span class="sw a" aria-hidden="true"></span>{{ aLabel }} <span class="sw b" aria-hidden="true"></span>{{ bLabel }}</p>
    <ChartTable :caption="title" :columns="['Session', aLabel, bLabel]" :rows="table" />
  </figure>
</template>

<style scoped>
.chart { margin: 0; display: grid; gap: 8px; }
figcaption { display: grid; gap: 2px; }
svg { width: 100%; height: auto; display: block; }
.axis { stroke: var(--border); }
.tick { font: 600 12px var(--ui); fill: var(--muted); }
.a { fill: var(--primary); }
.b { stroke: var(--text); stroke-width: 1; }
.col:focus { outline: 3px solid var(--text); outline-offset: 2px; }
.legend { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; }
.sw { display: inline-block; width: 14px; height: 14px; margin-right: 6px; vertical-align: -2px; border: 1px solid var(--text); }
.sw.a { background: var(--primary); }
.sw.b { background: repeating-linear-gradient(45deg, var(--text) 0 2px, var(--surface) 2px 5px); }
</style>
