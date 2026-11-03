<script setup>
import { ref } from "vue";
import Icon from "./Icon.vue";
import SwitchControl from "./SwitchControl.vue";
import { formatDate } from "../format.js";

defineProps({ items: { type: Array, required: true }, busyId: { type: String, default: "" } });
const emit = defineEmits(["toggle", "remove"]);
const confirming = ref("");
</script>

<template>
  <div class="table-wrap">
    <table class="data">
      <caption class="sr-only">Current assignments</caption>
      <thead>
        <tr><th scope="col">Passage</th><th scope="col">Class</th><th scope="col">Due</th><th scope="col">Sound Along</th><th scope="col"><span class="sr-only">Actions</span></th></tr>
      </thead>
      <tbody>
        <tr v-for="a in items" :key="a.id">
          <th scope="row" class="title"><a :href="`#/read/${encodeURIComponent(a.passageId)}`">{{ a.passageTitle }}</a></th>
          <td data-label="Class">{{ a.className }}</td>
          <td class="num" data-label="Due">{{ formatDate(a.dueDate) }}</td>
          <td data-label="Sound Along">
            <SwitchControl
              :model-value="a.soundAlong" :busy="busyId === a.id"
              :label="`Sound Along for ${a.passageTitle}, ${a.className}`"
              @update:model-value="emit('toggle', a, $event)"
            />
          </td>
          <td class="act">
            <div v-if="confirming === a.id" class="confirm" role="group" :aria-label="`Confirm delete ${a.passageTitle}`">
              <span class="small">Delete this assignment?</span>
              <button class="btn danger" type="button" @click="emit('remove', a); confirming = ''">Delete</button>
              <button class="btn" type="button" @click="confirming = ''">Cancel</button>
            </div>
            <button v-else class="btn ghost" type="button" :aria-label="`Delete assignment ${a.passageTitle} for ${a.className}`" @click="confirming = a.id">
              <Icon name="trash" :size="18" />
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
@media (max-width: 640px) {
  .table-wrap :deep(table.data), .table-wrap :deep(tbody) { display: block; }
  .table-wrap :deep(thead) { display: none; }
  .table-wrap :deep(tr) { display: grid; grid-template-columns: 1fr; gap: 6px; padding: var(--s2); border-bottom: 1px solid var(--border); }
  .table-wrap :deep(tr:last-child) { border-bottom: 0; }
  .table-wrap :deep(td), .table-wrap :deep(th[scope="row"]) { display: flex; align-items: center; justify-content: space-between; gap: var(--s1); padding: 0; border: 0; }
  .table-wrap :deep(td[data-label])::before { content: attr(data-label); font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
  /* the row header inherits the small uppercase column-header style; restore normal text */
  .table-wrap :deep(th[scope="row"]) { background: transparent; text-transform: none; letter-spacing: 0; font-size: 17px; white-space: normal; }
  .act { justify-content: flex-end; }
}
.title { font-weight: 600; text-align: left; }
.act { text-align: right; }
.confirm { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
</style>
