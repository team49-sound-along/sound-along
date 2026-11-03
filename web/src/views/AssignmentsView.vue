<script setup>
import { computed, ref, watch } from "vue";
import StateBlock from "../components/StateBlock.vue";
import AssignmentForm from "../components/AssignmentForm.vue";
import AssignmentsTable from "../components/AssignmentsTable.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import { route } from "../router.js";
import { role } from "../session.js";
import { prependAssignment, removeAssignment, replaceAssignment } from "../assignments.js";
import { formatDate } from "../format.js";

const { data, loading, error, reload } = useResource(async () => {
  const [passages, classes, assignments] = await Promise.all([api.passages(), api.classes(), api.assignments()]);
  return { passages, classes, assignments };
});
const items = ref([]);
watch(data, (d) => { if (d) items.value = d.assignments; });

const isTeacher = computed(() => role.value === "teacher");
const busyId = ref("");
const creating = ref(false);
const formError = ref("");
const actionError = ref("");
const flash = ref("");

async function create(body) {
  creating.value = true;
  formError.value = "";
  try {
    const created = await api.createAssignment(body);
    items.value = prependAssignment(items.value, created);
    flash.value = `Assigned "${created.passageTitle}" to ${created.className}.`;
  } catch (e) {
    formError.value = e.message;
  } finally {
    creating.value = false;
  }
}

async function toggle(assignment, soundAlong) {
  busyId.value = assignment.id;
  actionError.value = "";
  try {
    const updated = await api.setSoundAlong(assignment.id, soundAlong);
    items.value = replaceAssignment(items.value, updated);
  } catch (e) {
    actionError.value = `Could not update Sound Along for "${assignment.passageTitle}". ${e.message}`;
  } finally {
    busyId.value = "";
  }
}

async function remove(assignment) {
  actionError.value = "";
  try {
    await api.deleteAssignment(assignment.id);
    items.value = removeAssignment(items.value, assignment.id);
    flash.value = `Deleted the assignment for "${assignment.passageTitle}".`;
  } catch (e) {
    actionError.value = `Could not delete that assignment. ${e.message}`;
  }
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>{{ isTeacher ? "Assignments" : "My assignments" }}</h2>
        <p v-if="isTeacher">Assign a passage to a class and choose whether students get audio. Changes apply immediately.</p>
        <p v-else>Passages your teacher has assigned to you.</p>
      </div>
    </div>

    <StateBlock :loading="loading" :error="error" loading-label="Loading assignments" @retry="reload">
      <template v-if="data">
        <AssignmentForm
          v-if="isTeacher" :passages="data.passages" :classes="data.classes"
          :preset-passage-id="route.query.passageId || ''" :busy="creating" :error="formError" @submit="create"
        />
        <p class="sr-only" role="status" aria-live="polite">{{ flash }}</p>
        <p v-if="flash" class="notice ok">{{ flash }}</p>
        <p v-if="actionError" class="notice error" role="alert">{{ actionError }}</p>

        <section aria-labelledby="cur-h" class="stack">
          <h3 id="cur-h">{{ isTeacher ? "Current assignments" : "To read" }} ({{ items.length }})</h3>
          <div v-if="!items.length" class="card muted">
            {{ isTeacher ? "No assignments yet. Create one above." : "Nothing assigned yet. You can still read anything in the Library." }}
          </div>
          <div v-else-if="isTeacher" class="card flush">
            <AssignmentsTable :items="items" :busy-id="busyId" @toggle="toggle" @remove="remove" />
          </div>
          <ul v-else class="cards">
            <li v-for="a in items" :key="a.id" class="card">
              <h4>{{ a.passageTitle }}</h4>
              <p class="small muted">{{ a.className }} &middot; Due {{ formatDate(a.dueDate) }}</p>
              <p><span class="badge" :class="a.soundAlong ? 'teal' : ''">{{ a.soundAlong ? "Audio on" : "Text only" }}</span></p>
              <a class="btn primary" :href="`#/read/${encodeURIComponent(a.passageId)}`">Open</a>
            </li>
          </ul>
        </section>
      </template>
    </StateBlock>
  </div>
</template>

<style scoped>
.stack { display: grid; gap: var(--s2); }
.cards { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: var(--s2); }
.cards .card { display: grid; gap: 12px; justify-items: start; }
h4 { margin: 0; font-size: 18px; }
</style>
