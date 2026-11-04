<script setup>
import { computed } from "vue";
import Icon from "./Icon.vue";
import { isSpanish } from "../language.js";
import { passageSummary } from "../libraryMeta.js";
import { readTarget } from "../voices.js";
import { formatCount } from "../format.js";

const props = defineProps({
  passage: { type: Object, required: true },
  canAssign: Boolean,
  list: Boolean,
});
const summary = computed(() => (props.passage.isSeries ? `${props.passage.total} parts · ${formatCount(props.passage.words)} words` : passageSummary(props.passage)));
const firstPart = computed(() => (props.passage.isSeries ? props.passage.parts[0] : props.passage));
const created = computed(() => (props.passage.isSeries ? props.passage.parts.length : 0));
</script>

<template>
  <article class="pcard" :class="{ list }" :aria-labelledby="`p-${passage.id}`" :aria-describedby="`s-${passage.id}`">
    <div class="text">
      <h3 :id="`p-${passage.id}`">
        {{ passage.title }}
        <span v-if="isSpanish(passage)" class="badge teal" lang="es" title="Spanish passage">Español</span>
        <span v-if="passage.isSeries" class="badge teal" title="A long document in linked parts">{{ passage.total }} parts</span>
        <span v-if="passage.translationLangs?.length" class="badge teal" title="Also available in another language">Also in {{ passage.translationLangs.map((l) => (l === "es" ? "Español" : "English")).join(", ") }}</span>
      </h3>
      <p :id="`s-${passage.id}`" class="summary">{{ summary }}</p>
      <p v-if="passage.isSeries && created < passage.total" class="summary" role="status">{{ created }} of {{ passage.total }} parts are ready so far.</p>
      <details v-if="passage.isSeries" class="partlist">
        <summary>Parts</summary>
        <ol>
          <li v-for="(part, n) in passage.parts" :key="part.id">
            <a :href="`#/read/${encodeURIComponent(readTarget(part))}`">Part {{ part.series.index }}</a>
            <a v-if="canAssign" class="small" :href="`#/assignments?passageId=${encodeURIComponent(part.id)}`" :aria-label="`Assign part ${part.series.index} of ${passage.title}`">Assign</a>
          </li>
        </ol>
      </details>
    </div>
    <div class="actions">
      <a class="btn primary" :href="`#/read/${encodeURIComponent(readTarget(firstPart))}`" :aria-label="passage.isSeries ? `Read ${passage.title}, from part 1` : `Read ${passage.title}`">
        <Icon name="book" :size="18" /> {{ passage.isSeries ? "Read from part 1" : "Read" }}
      </a>
      <a v-if="canAssign && !passage.isSeries" class="btn" :href="`#/assignments?passageId=${encodeURIComponent(passage.id)}`" :aria-label="`Assign ${passage.title}`">
        <Icon name="assign" :size="18" /> Assign
      </a>
    </div>
  </article>
</template>

<style scoped>
.pcard { display: flex; flex-direction: column; gap: var(--s2); height: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: var(--s3); }
.text { display: grid; gap: 4px; min-width: 0; }
h3 { font-size: 20px; line-height: 1.3; font-weight: 700; overflow-wrap: anywhere; }
h3 .badge { vertical-align: middle; margin-left: 4px; }
.summary { color: var(--muted); font-size: 14px; line-height: 1.5; }
.partlist { font-size: 14px; }
.partlist summary { cursor: pointer; color: var(--primary); min-height: 32px; display: flex; align-items: center; }
.partlist ol { margin: 4px 0 0; padding-left: 20px; display: grid; gap: 4px; }
.partlist li { display: flex; gap: 12px; align-items: baseline; flex-wrap: wrap; }
.actions { display: flex; gap: var(--s1); flex-wrap: wrap; margin-top: auto; }
.pcard.list { flex-direction: row; align-items: center; justify-content: space-between; gap: var(--s3); height: auto; padding: var(--s2) var(--s3); }
.pcard.list .text { flex: 1 1 auto; }
.pcard.list .actions { flex: none; margin-top: 0; flex-wrap: nowrap; }
@media (max-width: 560px) {
  .pcard { padding: var(--s2); }
  .pcard.list { flex-direction: column; align-items: stretch; gap: var(--s2); }
  .pcard.list .actions { flex-wrap: wrap; }
  .actions .btn { flex: 1 1 auto; }
}
</style>
