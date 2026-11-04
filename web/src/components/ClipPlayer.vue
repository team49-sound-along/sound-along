<script setup>
// One anonymous clip: a labelled native audio player and its 1..5 rating. Never shows what the narrator is.
import { ref } from "vue";
import RadioGroup from "./RadioGroup.vue";
import { RATING_ENDS, RATING_VALUES } from "../listening.js";

defineProps({ id: String, label: String, url: String, rating: { default: null }, disabled: Boolean });
const emit = defineEmits(["update:rating"]);
const audio = ref(null);
const options = RATING_VALUES.map((v) => ({ value: v, label: String(v) }));
const hint = `${RATING_ENDS[1]}, ${RATING_ENDS[5]}`;
/** Stops playback and releases the file (used when moving to the next trial). */
function stop() {
  const a = audio.value;
  if (!a) return;
  a.pause();
  a.removeAttribute("src");
  a.load();
}
defineExpose({ stop, audio });
</script>

<template>
  <section class="clip card" :aria-labelledby="`${id}-h`">
    <h3 :id="`${id}-h`">{{ label }}</h3>
    <audio ref="audio" :src="url" controls preload="metadata" :aria-label="label"></audio>
    <RadioGroup :legend="`How natural does ${label} sound for reading along?`" :name="`${id}-rating`" :options="options" :model-value="rating" :hint="hint" :disabled="disabled" inline scale @update:model-value="emit('update:rating', $event)" />
  </section>
</template>

<style scoped>
.clip { display: grid; gap: var(--s2); }
audio { width: 100%; min-height: 44px; }
</style>
