<script setup>
// A progress ring: the share (0 to 100) that finished, with the number in the middle. Plain SVG; the sentence beside it carries the meaning.
import { computed } from "vue";

const props = defineProps({ percent: { type: Number, default: null }, size: { type: Number, default: 132 }, label: { type: String, default: "finished" } });
const STROKE = 14;
const radius = computed(() => (props.size - STROKE) / 2);
const circumference = computed(() => 2 * Math.PI * radius.value);
const dash = computed(() => (props.percent === null ? 0 : (Math.max(0, Math.min(100, props.percent)) / 100) * circumference.value));
const description = computed(() => (props.percent === null ? `Not enough reads yet` : `${props.percent}% ${props.label}`));
</script>

<template>
  <svg class="ring" :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" role="img" :aria-label="description">
    <circle class="track" :cx="size / 2" :cy="size / 2" :r="radius" :stroke-width="STROKE" fill="none" />
    <circle v-if="percent !== null" class="arc" :cx="size / 2" :cy="size / 2" :r="radius" :stroke-width="STROKE" fill="none" stroke-linecap="round" :stroke-dasharray="`${dash} ${circumference}`" :transform="`rotate(-90 ${size / 2} ${size / 2})`" />
    <text class="big" :x="size / 2" :y="size / 2 + (percent === null ? 6 : 2)" text-anchor="middle" :font-size="percent === null ? 14 : size * 0.26">{{ percent === null ? "Not yet" : `${percent}%` }}</text>
    <text v-if="percent !== null && size >= 110" class="cap" :x="size / 2" :y="size / 2 + size * 0.2" text-anchor="middle" :font-size="Math.max(12, size * 0.11)">{{ label }}</text>
  </svg>
</template>

<style scoped>
.ring { flex: none; }
.track { stroke: var(--surface-2); }
.arc { stroke: var(--primary); }
.big { fill: var(--text); font-weight: 700; font-family: var(--ui); }
.cap { fill: var(--muted); font-family: var(--ui); }
@media (prefers-reduced-motion: no-preference) { .arc { transition: stroke-dasharray 0.4s ease; } }
</style>
