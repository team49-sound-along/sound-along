<script setup>
import { computed, ref, watch } from "vue";
import StateBlock from "../components/StateBlock.vue";
import AssignmentForm from "../components/AssignmentForm.vue";
import AssignmentsTable from "../components/AssignmentsTable.vue";
import { api, passageIndex } from "../api.js";
import { useResource } from "../useResource.js";
import { route } from "../router.js";
import { role } from "../session.js";
import { prependAssignment, removeAssignment, replaceAssignment } from "../assignments.js";
import { formatDate } from "../format.js";

const { data, loading, error, reload } = useResource(async () => {
  const [passages, classes, assignments] = await Promise.all([passageIndex(), api.classes(), api.assignments()]);
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
const showForm = ref(Boolean(route.value.query?.passageId));

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
  if (!formError.value) showForm.value = false;
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
        <h2 class="title">{{ isTeacher ? "Assignments" : "My assignments" }}</h2>
        <p v-if="isTeacher">Switch Sound Along off for a class and its students see the text without audio.</p>
        <p v-else>Passages your teacher has assigned to you.</p>
      </div>
      <button
        v-if="isTeacher && data" class="btn primary" type="button"
        :aria-expanded="showForm" aria-controls="assign-form" @click="showForm = !showForm"
      >New assignment</button>
    </div>

    <StateBlock :loading="loading" :error="error" loading-label="Loading assignments" @retry="reload">
      <template v-if="data">
        <div v-if="isTeacher && showForm" id="assign-form">
          <AssignmentForm
            :passages="data.passages" :classes="data.classes"
            :preset-passage-id="route.query.passageId || ''" :busy="creating" :error="formError" @submit="create"
          />
        </div>
        <p class="sr-only" role="status" aria-live="polite">{{ flash }}</p>
        <p v-if="flash" class="notice ok">{{ flash }}</p>
        <p v-if="actionError" class="notice error" role="alert">{{ actionError }}</p>

        <section aria-labelledby="cur-h" class="stack">
          <h3 id="cur-h" :class="{ 'sr-only': isTeacher }">{{ isTeacher ? "Current assignments" : "To read" }} ({{ items.length }})</h3>
          <div v-if="!items.length" class="card muted">
            {{ isTeacher ? "No assignments yet. Choose New assignment to create one." : "Nothing assigned yet. You can still read anything in the Library." }}
          </div>
          <template v-else-if="isTeacher">
            <AssignmentsTable :items="items" :classes="data.classes" :busy-id="busyId" @toggle="toggle" @remove="remove" />
            <p class="small muted note">Students in a class with Sound Along off see the passage text without audio and without tap-to-replay.</p>
          </template>
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
.title { font-size: 32px; line-height: 1.15; letter-spacing: -0.03em; font-weight: 700; }
.note { max-width: 62ch; }
@media (max-width: 480px) { .title { font-size: 28px; } }
</style>
