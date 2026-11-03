<script setup>
import { computed, useId } from "vue";
import Icon from "./Icon.vue";
import { elapsedSeconds, stepStates } from "../jobSteps.js";
import { formatCount, formatMinutes, formatRtf, formatSeconds } from "../format.js";

const props = defineProps({ job: { type: Object, required: true }, now: { type: Number, required: true } });
const headId = useId();
const steps = computed(() => stepStates(props.job));
const elapsed = computed(() => elapsedSeconds(props.job.startedAt, props.job.finishedAt, props.now));
const m = computed(() => props.job.metrics ?? {});
const summary = computed(() => [
  { label: "Words", value: formatCount(m.value.words) },
  { label: "Audio length", value: formatMinutes(typeof m.value.audioSeconds === "number" ? m.value.audioSeconds / 60 : null) },
  { label: "Generation time", value: formatSeconds(m.value.generateSeconds) },
  { label: "Real-time factor", value: formatRtf(m.value.realTimeFactor) },
  { label: "Unaligned words", value: formatCount(m.value.unalignedWords) },
]);
</script>

<template>
  <section class="card tracker" :aria-labelledby="headId">
    <div class="head">
      <h3 :id="headId">{{ job.title }}</h3>
      <span class="elapsed num" aria-label="Elapsed time">{{ elapsed === null ? "—" : `${elapsed}s` }} elapsed</span>
    </div>
    <ol class="steps">
      <li v-for="(s, n) in steps" :key="s.key" :class="s.state" :aria-current="s.state === 'current' ? 'step' : undefined">
        <span class="dot" aria-hidden="true">
          <Icon v-if="s.state === 'done'" name="check" :size="16" />
          <Icon v-else-if="s.state === 'failed'" name="close" :size="16" />
          <template v-else>{{ n + 1 }}</template>
        </span>
        <span class="txt">
          <strong>{{ s.label }}</strong>
          <span class="small muted">{{ s.hint }}</span>
          <span class="sr-only">{{ s.state === "done" ? "complete" : s.state === "current" ? "in progress" : s.state === "failed" ? "failed" : "waiting" }}</span>
        </span>
      </li>
    </ol>

    <div v-if="job.status === 'failed'" class="notice error" role="alert">
      <p>{{ job.error || "Generation failed. Please try again." }}</p>
    </div>
    <div v-else-if="job.status === 'done'" class="result" role="status">
      <p class="notice ok"><strong>Ready.</strong> Audio and word timing were generated from your text.</p>
      <dl class="metrics">
        <div v-for="x in summary" :key="x.label"><dt>{{ x.label }}</dt><dd class="num">{{ x.value }}</dd></div>
      </dl>
      <p class="small muted">Source: job metrics from GET /api/jobs/{{ job.id }}.</p>
      <div v-if="job.humanPassageId && job.passageId" class="open-row">
        <a class="btn primary" :href="`#/read/${encodeURIComponent(job.humanPassageId)}`">Open with human narrator</a>
        <a class="btn" :href="`#/read/${encodeURIComponent(job.passageId)}`">Open with read-aloud voice</a>
      </div>
      <a v-else-if="job.passageId" class="btn primary" :href="`#/read/${encodeURIComponent(job.passageId)}`">Open in reader</a>
    </div>
    <p v-else class="small muted" role="status">Working&hellip; this page updates automatically.</p>
  </section>
</template>

<style scoped>
.tracker { display: grid; gap: var(--s3); }
.head { display: flex; justify-content: space-between; gap: var(--s2); flex-wrap: wrap; align-items: baseline; }
.elapsed { color: var(--muted); font-size: 14px; }
.steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: var(--s2); }
.steps li { display: flex; gap: 12px; align-items: flex-start; padding: 12px; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface-2); }
.steps li.current { border-color: var(--primary); background: var(--primary-soft); box-shadow: 0 0 0 1px var(--primary); }
.steps li.failed { border-color: var(--danger); background: var(--danger-soft); }
.dot { flex: none; display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; border: 2px solid var(--muted); font-size: 13px; font-weight: 700; color: var(--muted); }
.current .dot { border-color: var(--primary); background: var(--hl); color: var(--on-hl); animation: pulse 1.4s ease-in-out infinite; }
li.done .dot { border-color: var(--primary); background: var(--primary); color: var(--on-primary); }
.failed .dot { border-color: var(--danger); color: var(--danger); }
.txt { display: grid; gap: 2px; min-width: 0; }
.metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: var(--s2); margin: 0; }
.metrics dt { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; font-weight: 700; color: var(--muted); }
.metrics dd { margin: 0; font-size: 22px; font-weight: 700; }
.result { display: grid; gap: var(--s2); justify-items: start; }
.open-row { display: flex; gap: var(--s1); flex-wrap: wrap; }
.result .notice, .result .metrics { width: 100%; }
@keyframes pulse { 50% { box-shadow: 0 0 0 5px color-mix(in srgb, var(--hl) 45%, transparent); } }
@media (max-width: 760px) { .steps { grid-template-columns: minmax(0, 1fr); } }
</style>
