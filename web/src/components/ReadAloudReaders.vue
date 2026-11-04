<script setup>
// "Who needs a hand?" (only mounted when the school switched on anonymous reader codes for a class): a plain list of readers, one bar each for how
// much of the passage they read last time, with one word. A reader is a random code from one device, not a name. Letter order, never ranked.
import { computed, watch } from "vue";
import StateBlock from "./StateBlock.vue";
import HBarChart from "./HBarChart.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import { readerRows } from "../readAloudView.js";

const props = defineProps({ classId: { type: String, required: true }, className: { type: String, required: true }, passageId: { type: String, default: "" } });
const { data, loading, error, reload } = useResource(() => api.readAloudReaders({ classId: props.classId, code: "", passageId: props.passageId }));
watch([() => props.classId, () => props.passageId], reload);
const rows = computed(() => readerRows(data.value?.progress));
</script>

<template>
  <section class="stack" aria-labelledby="rr-h" data-testid="ra-readers">
    <h4 id="rr-h">Who needs a hand?</h4>
    <StateBlock :loading="loading && !data" :error="error" loading-label="Loading readers" @retry="reload">
      <template v-if="data">
        <p v-if="!data.enabled" class="notice" role="note">Progress by reader is off for this class.</p>
        <p v-else-if="!data.enough" class="notice" role="note" data-testid="ra-readers-few">Once 3 different readers have read aloud in this class, a bar for each will show here.</p>
        <template v-else>
          <div data-testid="ra-reader-bars">
            <HBarChart :title="`How much of the passage each reader read, ${className}`" :rows="rows" :max="1" column="Passage read" :show-table="false" hide-title />
          </div>
          <p class="small muted">Each bar is one device, not a name: how much of the passage it read last time.</p>
        </template>
      </template>
    </StateBlock>
  </section>
</template>

<style scoped>
.stack { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--s2); }
h4 { font-size: 18px; margin: 0; }
</style>
