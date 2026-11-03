<script setup>
import { ref } from "vue";
import SwitchControl from "./SwitchControl.vue";
import { assignmentMeta, soundAlongLabel } from "../assignmentMeta.js";

defineProps({
  items: { type: Array, required: true },
  classes: { type: Array, default: () => [] },
  busyId: { type: String, default: "" },
});
const emit = defineEmits(["toggle", "remove"]);
const confirming = ref("");
</script>

<template>
  <ul class="rows">
    <li v-for="a in items" :key="a.id" class="row">
      <div class="main">
        <a class="title" :href="`#/read/${encodeURIComponent(a.passageId)}`">{{ a.passageTitle }}</a>
        <p class="meta muted">{{ assignmentMeta(a, classes) }}</p>
      </div>
      <div class="switch">
        <SwitchControl
          :model-value="a.soundAlong" :busy="busyId === a.id"
          :label="`Sound Along for ${a.passageTitle}, ${a.className}`"
          @update:model-value="emit('toggle', a, $event)"
        />
        <span class="sw-text" aria-hidden="true">{{ soundAlongLabel(a.soundAlong) }}</span>
      </div>
      <div class="act">
        <div v-if="confirming === a.id" class="confirm" role="group" :aria-label="`Confirm delete ${a.passageTitle}`">
          <span class="small">Delete this assignment?</span>
          <button class="btn danger" type="button" @click="emit('remove', a); confirming = ''">Delete</button>
          <button class="btn" type="button" @click="confirming = ''">Cancel</button>
        </div>
        <button v-else class="btn" type="button" :aria-label="`Remove assignment ${a.passageTitle} for ${a.className}`" @click="confirming = a.id">Remove</button>
      </div>
    </li>
  </ul>
</template>

<style scoped>
.rows { list-style: none; margin: 0; padding: 0; }
.row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: var(--s3); padding: var(--s3) 0; border-bottom: 1px solid var(--border); }
.row:first-child { border-top: 1px solid var(--border); }
.main { min-width: 0; }
.title { font-size: 20px; font-weight: 600; line-height: 1.3; color: var(--text); text-decoration: none; overflow-wrap: anywhere; }
.title:hover { color: var(--primary); text-decoration: underline; }
.meta { margin-top: 4px; font-size: 14px; overflow-wrap: anywhere; }
.switch { display: flex; align-items: center; gap: var(--s1); font-weight: 600; white-space: nowrap; }
.act { display: flex; justify-content: flex-end; }
.confirm { display: flex; align-items: center; gap: var(--s1); flex-wrap: wrap; justify-content: flex-end; }
@media (max-width: 720px) {
  .row { grid-template-columns: minmax(0, 1fr); gap: var(--s1); padding: var(--s2) 0; }
  .act, .confirm { justify-content: flex-start; }
}
</style>
