<script setup>
import { ref } from "vue";
import { validateTextFile } from "../files.js";
import { ImportError, importFile } from "../import/index.js";
import { TITLE_MAX } from "../validation.js";

defineProps({ disabled: Boolean });
const emit = defineEmits(["loaded"]);
const dragging = ref(false);
const error = ref("");
const status = ref("");
const input = ref(null);
const busy = ref(false);

async function take(file) {
  error.value = "";
  status.value = "";
  const check = validateTextFile(file);
  if (!check.ok) {
    error.value = check.error;
    return;
  }
  busy.value = true;
  status.value = `Reading ${file.name}\u2026`;
  try {
    const { title, text } = await importFile(file);
    emit("loaded", { title: title.slice(0, TITLE_MAX), text });
    status.value = `Loaded ${file.name}. Please check the text below, then edit the title or text if you need to.`;
  } catch (e) {
    status.value = "";
    error.value = e instanceof ImportError ? e.message : "That file could not be read. Try another file, or paste the text instead.";
  } finally {
    busy.value = false;
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
    <label for="g-file" class="label">Add a file (optional)</label>
    <input id="g-file" ref="input" class="input" type="file" accept=".txt,.md,.docx,.pdf,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/pdf" :disabled="disabled || busy" aria-describedby="g-file-help g-file-msg" @change="onPick" />
    <p id="g-file-help" class="small muted">Choose or drop a Word (.docx), PDF, .txt or .md file, or paste text below. Files are read on this computer and are not uploaded.</p>
    <p id="g-file-msg" class="small" :class="error ? 'error-text' : 'muted'" :role="error ? 'alert' : 'status'">{{ error || status }}</p>
  </div>
</template>

<style scoped>
.drop { display: grid; gap: 6px; padding: var(--s2); border: 2px dashed var(--border); border-radius: var(--r); background: var(--surface-2); min-width: 0; }
.drop.dragging { border-color: var(--primary); background: var(--primary-soft); }
.drop p { min-height: 0; }
</style>
