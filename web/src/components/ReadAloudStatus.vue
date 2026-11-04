<script setup>
// "Did they finish?": one big percentage ring for a class, or one plain bar per class for all classes, with one plain sentence under it.
import { computed } from "vue";
import ProgressRing from "./ProgressRing.vue";
import HBarChart from "./HBarChart.vue";
import { classRateRows } from "../readAloudView.js";
import { finishSplit } from "../readAloudStory.js";

const props = defineProps({ totals: { type: Object, required: true }, classes: { type: Array, default: () => [] }, byClass: Boolean });
const split = computed(() => finishSplit(props.totals));
const sentence = computed(() => (split.value ? `${split.value.finished} of ${split.value.total} finished. ${split.value.stopped} stopped part-way.` : ""));
</script>

<template>
  <div class="status" data-testid="ra-status">
    <HBarChart v-if="byClass" title="Finished, by class" :rows="classRateRows(classes, 'finishRate', 'finished')" :max="1" column="Finished" :show-table="false" hide-title />
    <ProgressRing v-else-if="split" :percent="split.finishedPercent" :size="160" />
    <p class="small muted">{{ sentence }}</p>
  </div>
</template>

<style scoped>
.status { display: grid; gap: var(--s1); justify-items: start; min-width: 0; }
.status > :first-child { justify-self: stretch; }
.status > svg { justify-self: start; }
</style>
