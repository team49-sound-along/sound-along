<script setup>
import { computed } from "vue";
import ChartTable from "./ChartTable.vue";
import { areaOf, linePoints, pathOf } from "../chartData.js";

// points: [{ label, value|null, text }]. Hand-written SVG: a line with a marker per step, each marker focusable and named, plus a table.
const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: "" },
  points: { type: Array, required: true },
  max: { type: Number, default: undefined }, // a fixed top of the scale (100 for percentages)
  column: { type: String, default: "Value" },
  area: Boolean,
});

const W = 560, H = 200;
const geo = computed(() => linePoints(props.points.map((p) => p.value), props.points.map((p) => p.label), { width: W, height: H, max: props.max }));
const ticks = computed(() => [0, geo.value.max / 2, geo.value.max].map((v) => ({ v, y: geo.value.baseline - (v / geo.value.max) * (geo.value.baseline - 12) })));
const text = (i) => props.points[i].text ?? "no data";
const summary = computed(() => `${props.title}: ${props.points.map((p, i) => `${p.label} ${text(i)}`).join("; ")}`);
const rows = computed(() => props.points.map((p, i) => [p.label, text(i)]));
const every = computed(() => Math.ceil(props.points.length / 6));
</script>

<template>
  <figure class="chart">
    <figcaption><strong>{{ title }}</strong><span v-if="subtitle" class="small muted">{{ subtitle }}</span></figcaption>
    <svg :viewBox="`0 0 ${W} ${H}`" role="group" :aria-label="summary" preserveAspectRatio="xMinYMin meet">
      <g v-for="t in ticks" :key="t.v">
        <line :x1="geo.left" :x2="geo.right" :y1="t.y" :y2="t.y" class="grid" />
        <text :x="geo.left - 6" :y="t.y + 4" class="tick" text-anchor="end">{{ Math.round(t.v) }}</text>
      </g>
      <template v-for="(seg, n) in geo.segments" :key="n">
        <path v-if="area && seg.length > 1" :d="areaOf(seg, geo.baseline)" class="area" />
        <path v-if="seg.length > 1" :d="pathOf(seg)" class="line" />
      </template>
      <g v-for="(p, i) in geo.points" :key="i">
        <text v-if="i % every === 0 || i === geo.points.length - 1" :x="p.x" :y="H - 8" class="tick" text-anchor="middle">{{ p.label }}</text>
        <rect v-if="p.y !== null" :x="p.x - 5" :y="p.y - 5" width="10" height="10" :transform="`rotate(45 ${p.x} ${p.y})`" class="dot" tabindex="0" role="img" :aria-label="`${p.label}: ${text(i)}`"><title>{{ p.label }}: {{ text(i) }}</title></rect>
      </g>
    </svg>
    <ChartTable :caption="title" :columns="['When', column]" :rows="rows" />
  </figure>
</template>

<style scoped>
.chart { margin: 0; display: grid; gap: 8px; }
figcaption { display: grid; gap: 2px; }
svg { width: 100%; height: auto; display: block; }
.grid { stroke: var(--border); stroke-width: 1; }
.tick { font: 600 12px var(--ui); fill: var(--muted); }
.line { fill: none; stroke: var(--primary); stroke-width: 3; stroke-linejoin: round; }
.area { fill: var(--primary-soft); opacity: 0.8; }
.dot { fill: var(--surface); stroke: var(--primary); stroke-width: 2.5; }
.dot:focus { outline: none; fill: var(--hl); stroke: var(--text); stroke-width: 3; }
</style>
