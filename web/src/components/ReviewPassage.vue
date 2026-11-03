<script setup>
import { ref } from "vue";
import JobTracker from "./JobTracker.vue";
import { api } from "../api.js";
import { fixHref } from "../review.js";
import { useJobPoll } from "../useJobPoll.js";

const props = defineProps({ item: { type: Object, required: true } });
const emit = defineEmits(["dismiss"]);
const { job, now, pollError, running, start } = useJobPoll();
const starting = ref(false);
const error = ref("");

async function regenerate() {
  starting.value = true;
  error.value = "";
  try {
    const { jobId } = await api.regenerate(props.item.passageId);
    start(jobId, props.item.title);
  } catch (e) {
    error.value =
      e.status === 404 ? "This passage has no saved source text, so it cannot be regenerated." : e.status === 429 ? "Too many requests right now. Wait a minute, then try again." : e.message;
  } finally {
    starting.value = false;
  }
}
</script>

<template>
  <section class="card passage" :aria-labelledby="`rp-${item.passageId}`">
    <div class="head">
      <h3 :id="`rp-${item.passageId}`">{{ item.title }}</h3>
      <a class="small" :href="`#/read/${encodeURIComponent(item.passageId)}`">Listen to this passage</a>
    </div>
    <ul class="suspects">
      <li v-for="s in item.suspects" :key="s.expected">
        <div class="said">
          <p><span class="label">Text says</span> <strong class="word">{{ s.expected }}</strong></p>
          <p><span class="label">Check heard</span> <strong class="word">{{ s.heard }}</strong></p>
        </div>
        <div class="btns">
          <a class="btn" :href="fixHref(s.expected)" :aria-label="`Fix pronunciation of ${s.expected}`">Fix pronunciation</a>
          <button class="btn" type="button" :aria-label="`Dismiss ${s.expected}`" @click="emit('dismiss', s.expected)">Dismiss</button>
        </div>
      </li>
    </ul>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <div>
      <button class="btn primary" type="button" :disabled="starting || running" @click="regenerate">{{ starting || running ? "Regenerating..." : "Regenerate with current fixes" }}</button>
    </div>
    <p v-if="pollError" class="notice error" role="alert">{{ pollError }}</p>
    <JobTracker v-if="job" :job="job" :now="now" />
  </section>
</template>

<style scoped>
.passage { display: grid; gap: var(--s2); }
.head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: var(--s1); }
.suspects { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s1); }
.suspects li { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: var(--s1) var(--s2); padding: 12px; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface-2); min-width: 0; }
.said { display: grid; gap: 2px; min-width: 0; }
.said .label { display: inline-block; min-width: 84px; font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.word { overflow-wrap: anywhere; }
.btns { display: flex; gap: var(--s1); flex-wrap: wrap; }
</style>
