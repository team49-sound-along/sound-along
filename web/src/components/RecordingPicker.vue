<script setup>
import { ref } from "vue";
import { formatBytes, validateRecording } from "../files.js";

defineProps({ disabled: Boolean, file: { type: Object, default: null } });
const emit = defineEmits(["update:file"]);
const error = ref("");

function onPick(e) {
  const f = e.target.files?.[0];
  error.value = "";
  if (!f) return emit("update:file", null);
  const check = validateRecording(f);
  if (!check.ok) {
    error.value = check.error;
    e.target.value = "";
    return emit("update:file", null);
  }
  emit("update:file", f);
}
function clear() {
  error.value = "";
  const el = document.getElementById("g-rec");
  if (el) el.value = "";
  emit("update:file", null);
}
</script>

<template>
  <div class="field">
    <label for="g-rec">Add your own recording (optional)</label>
    <input id="g-rec" class="input" type="file" accept="audio/mpeg,audio/wav,audio/mp4,audio/x-m4a,audio/webm,.mp3,.wav,.m4a,.mp4,.webm" :disabled="disabled" aria-describedby="g-rec-help g-rec-msg" @change="onPick" />
    <p id="g-rec-help" class="small muted">Read the passage aloud and upload it (MP3, WAV, M4A/MP4 or WebM, up to 25 MB). Students can then choose your voice or the computer-generated read-aloud voice.</p>
    <p id="g-rec-msg" class="small" :class="error ? 'error-text' : 'muted'" :role="error ? 'alert' : 'status'">
      {{ error || (file ? `Selected: ${file.name} (${formatBytes(file.size)})` : "") }}
      <button v-if="file && !disabled" class="btn ghost" type="button" @click="clear">Remove recording</button>
    </p>
  </div>
</template>
