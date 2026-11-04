<script setup>
import { computed, ref, watch } from "vue";
import SwitchControl from "./SwitchControl.vue";
import { gradeLabel } from "../assignmentMeta.js";

const props = defineProps({
  passages: { type: Array, required: true },
  classes: { type: Array, required: true },
  presetPassageId: { type: String, default: "" },
  busy: Boolean,
  error: { type: String, default: "" },
});
const emit = defineEmits(["submit"]);

const passageId = ref(props.passages.some((p) => p.id === props.presetPassageId) ? props.presetPassageId : "");
const classId = ref("");
const soundAlong = ref(true);
const dueDate = ref("");
const touched = ref(false);

const missing = computed(() => !passageId.value || !classId.value);
watch(() => props.presetPassageId, (id) => { if (props.passages.some((p) => p.id === id)) passageId.value = id; });

function submit() {
  touched.value = true;
  if (missing.value) return;
  emit("submit", { passageId: passageId.value, classId: classId.value, soundAlong: soundAlong.value, ...(dueDate.value ? { dueDate: dueDate.value } : {}) });
}
</script>

<template>
  <form class="card form" novalidate @submit.prevent="submit">
    <h3>New assignment</h3>
    <div class="row">
      <div class="field">
        <label for="a-passage">Passage</label>
        <select id="a-passage" v-model="passageId" class="input" :aria-invalid="touched && !passageId" required>
          <option value="" disabled>Select a passage</option>
          <option v-for="p in passages" :key="p.id" :value="p.id">{{ p.title }}</option>
        </select>
        <span v-if="touched && !passageId" class="error-text">Choose a passage.</span>
      </div>
      <div class="field">
        <label for="a-class">Class</label>
        <select id="a-class" v-model="classId" class="input" :aria-invalid="touched && !classId" required>
          <option value="" disabled>Select a class</option>
          <option v-for="c in classes" :key="c.id" :value="c.id">{{ c.name }} ({{ gradeLabel(c.grade) }}, {{ c.students }} students)</option>
        </select>
        <span v-if="touched && !classId" class="error-text">Choose a class.</span>
      </div>
      <div class="field">
        <label for="a-due">Due date (optional)</label>
        <input id="a-due" v-model="dueDate" class="input" type="date" />
      </div>
    </div>
    <div class="foot">
      <SwitchControl v-model="soundAlong" label="Sound Along audio" show-label />
      <button class="btn primary" type="submit" :disabled="busy">{{ busy ? "Assigning..." : "Assign passage" }}</button>
    </div>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
  </form>
</template>

<style scoped>
.form { display: grid; gap: var(--s2); }
.row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: var(--s2); }
.foot { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: var(--s2); }
</style>
