<script setup>
// Plays a short pre-recorded sample of a voice (web/public/voice-samples/<id>.mp3, or polly-<VoiceId>.mp3 for Amazon Polly voices; made by
// scripts/build_voice_samples.py and scripts/build_polly_voice_samples.py). A missing file shows a calm note instead of a broken player.
import { onBeforeUnmount, ref, watch } from "vue";
import Icon from "./Icon.vue";
import { sampleFile } from "../settings.js";

const props = defineProps({ voice: { type: String, default: "" }, engine: { type: String, default: "" }, label: { type: String, default: "" }, autoplay: Boolean });
const state = ref("idle"); // idle | playing | missing
let audio = null;

function stop() {
  if (audio) {
    audio.pause();
    audio = null;
  }
  if (state.value === "playing") state.value = "idle";
}
function play() {
  stop();
  if (!props.voice) return;
  audio = new Audio(`/voice-samples/${encodeURIComponent(sampleFile(props.voice, props.engine))}.mp3`);
  audio.addEventListener("ended", () => (state.value = "idle"));
  audio.addEventListener("error", () => (state.value = "missing"));
  state.value = "playing";
  audio.play().catch(() => { if (state.value === "playing") state.value = "idle"; }); // a missing file is reported by the error event, which must not be overwritten
}
// Choosing another voice plays it straight away (the choice is a user action, so the browser allows the sound).
watch(() => props.voice, (next, prev) => {
  if (props.autoplay && prev) play();
  else { stop(); state.value = "idle"; }
});
onBeforeUnmount(stop);
defineExpose({ play });
</script>

<template>
  <span class="sample">
    <button class="btn" type="button" :disabled="!voice" :aria-label="state === 'playing' ? `Stop ${label} sample` : `Play ${label} sample`" @click="state === 'playing' ? stop() : play()">
      <Icon :name="state === 'playing' ? 'close' : 'play'" :size="18" /> {{ state === "playing" ? "Stop" : "Hear it" }}
    </button>
    <span v-if="state === 'missing'" class="small muted" role="status">Sample not available yet.</span>
  </span>
</template>

<style scoped>
.sample { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sample .btn { min-width: 112px; justify-content: center; }
</style>
