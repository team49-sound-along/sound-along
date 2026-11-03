<script setup>
import { ref } from "vue";
import { titleFromFilename, validateTextFile } from "../files.js";
import { TITLE_MAX } from "../validation.js";

defineProps({ disabled: Boolean });
const emit = defineEmits(["loaded"]);
const dragging = ref(false);
const error = ref("");
const status = ref("");
const input = ref(null);

async function take(file) {
  error.value = "";
  status.value = "";
  const check = validateTextFile(file);
  if (!check.ok) {
    error.value = check.error;
    return;
  }
  try {
    const text = await file.text();
    emit("loaded", { title: titleFromFilename(file.name, TITLE_MAX), text });
    status.value = `Loaded ${file.name}. You can still edit the title and text below.`;
  } catch {
    error.value = "That file could not be read. Try another file, or paste the text instead.";
  }
}
function onPick(e) {
  take(e.target.files?.[0]);
  e.target.value = "";
}
function onDrop(e) {
  dragging.value = false;
  if (!e.dataTransfer?.files?.length) return;
  take(e.dataTransfer.files[0]);
}
</script>

<template>
  <div class="drop" :class="{ dragging }" @dragover.prevent="dragging = !disabled" @dragleave="dragging = false" @drop.prevent="!disabled && onDrop($event)">
    <label for="g-file" class="label">Add a text file (optional)</label>
    <input id="g-file" ref="input" class="input" type="file" accept=".txt,.md,text/plain,text/markdown" :disabled="disabled" aria-describedby="g-file-help g-file-msg" @change="onPick" />
    <p id="g-file-help" class="small muted">Choose or drop a .txt or .md file up to 100 KB. Or paste text below.</p>
    <p id="g-file-msg" class="small" :class="error ? 'error-text' : 'muted'" :role="error ? 'alert' : 'status'">{{ error || status }}</p>
  </div>
</template>

<style scoped>
.drop { display: grid; gap: 6px; padding: var(--s2); border: 2px dashed var(--border); border-radius: var(--r); background: var(--surface-2); min-width: 0; }
.drop.dragging { border-color: var(--primary); background: var(--primary-soft); }
.drop p { min-height: 0; }
</style>
