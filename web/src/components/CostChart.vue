<script setup>
import { computed, useId } from "vue";
import { formatUsd, DASH } from "../format.js";

// rows: [{ key, label, value, estimated }]. Plain SVG horizontal bars, each chart on its own scale.
const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: "" },
  rows: { type: Array, required: true },
});

const uid = useId();
const W = 560, ROW = 44, PAD_L = 8, PAD_R = 92, BAR_H = 24;
const max = computed(() => Math.max(0, ...props.rows.map((r) => (Number.isFinite(r.value) ? r.value : 0))));
const bars = computed(() =>
  props.rows.map((r, n) => {
    const ok = Number.isFinite(r.value);
    const width = ok && max.value > 0 ? Math.max(2, (r.value / max.value) * (W - PAD_L - PAD_R)) : 0;
    return { ...r, y: n * ROW + 20, width, text: ok ? formatUsd(r.value) : DASH };
  }),
);
const height = computed(() => props.rows.length * ROW + 8);
const summary = computed(() => `${props.title}: ${bars.value.map((b) => `${b.label} ${b.text}${b.estimated ? " (estimate)" : ""}`).join("; ")}`);
</script>

<template>
  <figure class="chart">
    <figcaption>
      <strong>{{ title }}</strong>
      <span v-if="subtitle" class="small muted">{{ subtitle }}</span>
    </figcaption>
    <svg :viewBox="`0 0 ${W} ${height}`" role="img" :aria-label="summary" preserveAspectRatio="xMinYMin meet">
      <defs>
        <pattern :id="`hatch-${uid}`" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="8" height="8" fill="var(--primary-soft)" /><rect width="4" height="8" fill="var(--primary)" />
        </pattern>
      </defs>
      <g v-for="b in bars" :key="b.key">
        <text :x="PAD_L" :y="b.y - 6" class="lbl">{{ b.label }}{{ b.estimated ? " (estimate)" : "" }}</text>
        <rect :x="PAD_L" :y="b.y" :width="b.width" :height="BAR_H" rx="6" :class="['bar', b.key]" :fill="b.estimated ? `url(#hatch-${uid})` : undefined" />
        <text :x="PAD_L + b.width + 8" :y="b.y + 17" class="val">{{ b.text }}</text>
      </g>
    </svg>
  </figure>
</template>

<style scoped>
.chart { margin: 0; display: grid; gap: 8px; }
figcaption { display: grid; gap: 2px; }
svg { width: 100%; height: auto; display: block; }
.lbl { font: 600 13px var(--ui); fill: var(--muted); }
.val { font: 700 14px var(--ui); fill: var(--text); font-variant-numeric: tabular-nums; }
.bar.neural { fill: var(--primary); }
.bar.standard { fill: #6f8796; }
@media (prefers-color-scheme: dark) { .bar.standard { fill: #8fa6b4; } }
</style>
