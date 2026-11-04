<script setup>
// The school's switches for reading aloud, with the plain-language disclosure beside them. The student sees no consent screen: the school
// decides here, per class, and each switch is saved as soon as it is changed.
import { computed, ref } from "vue";
import SwitchControl from "./SwitchControl.vue";
import { api } from "../api.js";

const props = defineProps({ view: { type: Object, required: true } });
const emit = defineEmits(["change"]);

const busy = ref("");
const error = ref("");
const readers = computed(() => props.view.readersAvailable === true);

async function set(classId, field, value) {
  busy.value = `${classId ?? "all"}:${field}`;
  error.value = "";
  try {
    emit("change", await api.saveReadAloudSettings({ ...(classId ? { classId } : {}), [field]: value }));
  } catch (e) {
    error.value = e?.message || "That change was not saved. Please try again.";
  } finally {
    busy.value = "";
  }
}
const isBusy = (classId, field) => busy.value === `${classId ?? "all"}:${field}`;
</script>

<template>
  <div class="controls stack">
    <div class="notice" role="note" data-testid="ra-disclosure">
      <div class="stack">
        <strong>Before you turn this on for a class</strong>
        <ul class="small">
          <li>Reading aloud uses the browser&rsquo;s built-in speech service: Google in Chrome and Edge, Apple in Safari. That service hears the student&rsquo;s voice while the microphone is on.</li>
          <li>Sound Along never records or stores audio, and never stores what was said.</li>
          <li>Only anonymous word counts are kept: no names and no accounts.</li>
          <li><strong>Check your school&rsquo;s privacy policy before enabling this for young children.</strong></li>
        </ul>
      </div>
    </div>

    <div class="table-wrap" tabindex="0" role="region" aria-label="Reading aloud switches by class">
      <table class="data">
        <thead>
          <tr>
            <th scope="col">Class</th>
            <th scope="col">Read aloud with the microphone</th>
            <th scope="col">Share anonymous word counts with the teacher</th>
            <th v-if="readers" scope="col">Show progress by reader (anonymous codes)</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">All classes (default)</th>
            <td><SwitchControl :model-value="view.defaults.mic" label="All classes: Read aloud with the microphone" :busy="isBusy(null, 'mic')" @update:model-value="set(null, 'mic', $event)" /></td>
            <td><SwitchControl :model-value="view.defaults.share" label="All classes: Share anonymous word counts with the teacher" :busy="isBusy(null, 'share')" @update:model-value="set(null, 'share', $event)" /></td>
            <td v-if="readers"><SwitchControl :model-value="view.defaults.readers" label="All classes: Show progress by reader" :busy="isBusy(null, 'readers')" @update:model-value="set(null, 'readers', $event)" /></td>
          </tr>
          <tr v-for="c in view.classes" :key="c.id">
            <th scope="row">{{ c.name }}</th>
            <td><SwitchControl :model-value="c.mic" :label="`${c.name}: Read aloud with the microphone`" :busy="isBusy(c.id, 'mic')" @update:model-value="set(c.id, 'mic', $event)" /></td>
            <td><SwitchControl :model-value="c.share" :label="`${c.name}: Share anonymous word counts with the teacher`" :busy="isBusy(c.id, 'share')" @update:model-value="set(c.id, 'share', $event)" /></td>
            <td v-if="readers"><SwitchControl :model-value="c.readers" :label="`${c.name}: Show progress by reader`" :busy="isBusy(c.id, 'readers')" @update:model-value="set(c.id, 'readers', $event)" /></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p class="small muted">The first row is the default for every class that has not been changed on its own row. When the microphone is off for a class, students there do not see the button. When sharing is off, nothing is sent.</p>
    <p v-if="readers" class="small muted" data-testid="ra-readers-note">
      Progress by reader is off unless you turn it on, and it needs sharing. Each device makes a random code. Codes are not names. A shared classroom device counts as one reader.
      A student can tap &ldquo;Start a new reader code&rdquo; in the read-aloud panel. You can only match a code to a student if the student tells you.
    </p>
    <p v-else class="small muted">Progress by reader is not available on this site yet.</p>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.stack { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--s2); }
ul { margin: 0; padding-left: 20px; display: grid; gap: 4px; }
td { vertical-align: middle; }
.table-wrap { position: relative; } /* a positioned wrapper also clips the hidden "On/Off" labels, which would otherwise widen the page */
</style>
