<script setup>
import { computed } from "vue";
import StateBlock from "../components/StateBlock.vue";
import Reader from "../components/Reader.vue";
import { api, fetchTiming } from "../api.js";
import { route } from "../router.js";
import { role } from "../session.js";
import { useResource } from "../useResource.js";
import { soundAlongAllowed } from "../assignments.js";

const id = route.value.params.id;

// Assignments are best-effort: if they fail to load, the reader still works with audio on.
async function loadAll() {
  const [timing, assignments] = await Promise.all([fetchTiming(id), api.assignments().catch(() => [])]);
  return { timing, assignments };
}
const { data, loading, error, reload } = useResource(loadAll);

// An assignment is made against one passage id, but a text can have an AI and a human variant: honour both.
const ids = computed(() => [id, data.value?.timing.pairId].filter(Boolean));
const soundAlong = computed(() => (data.value ? ids.value.every((pid) => soundAlongAllowed(data.value.assignments, pid, role.value)) : true));
const classId = computed(() => data.value?.assignments.find((a) => ids.value.includes(a.passageId))?.classId);
</script>

<template>
  <div class="page reader-page">
    <StateBlock :loading="loading" :error="error" loading-label="Loading passage" @retry="reload">
      <Reader v-if="data" :passage-id="id" :timing="data.timing" :sound-along="soundAlong" :class-id="classId" />
    </StateBlock>
  </div>
</template>

<style scoped>
.reader-page { max-width: 1120px; padding-top: var(--s3); gap: var(--s2); }
</style>
