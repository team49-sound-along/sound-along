<script setup>
import Icon from "./Icon.vue";
import { formatCount, formatDuration } from "../format.js";
import { isSpanish } from "../language.js";
import { readTarget, voiceLabel } from "../voices.js";

defineProps({
  passage: { type: Object, required: true },
  canAssign: Boolean,
  list: Boolean,
});
</script>

<template>
  <article class="pcard" :class="{ list }" :aria-labelledby="`p-${passage.id}`">
    <div class="top">
      <span class="badge" :class="passage.source === 'generated' ? 'teal' : ''">{{ passage.source === "generated" ? "Generated" : "Sample" }}</span>
      <span class="badge" title="Narration">{{ passage.humanId ? "Human + read-aloud voice" : voiceLabel(passage.engine) }}</span>
      <span v-if="isSpanish(passage)" class="badge hl" lang="es" title="Spanish passage">Español</span>
    </div>
    <h3 :id="`p-${passage.id}`">{{ passage.title }}</h3>
    <dl class="meta">
      <div><dt>Words</dt><dd class="num">{{ formatCount(passage.words) }}</dd></div>
      <div><dt>Duration</dt><dd class="num">{{ formatDuration(passage.durationMs) }}</dd></div>
      <div><dt>Vocab</dt><dd class="num">{{ formatCount(passage.vocabCount) }}</dd></div>
    </dl>
    <div class="actions">
      <a class="btn primary" :href="`#/read/${encodeURIComponent(readTarget(passage))}`" :aria-label="`Read ${passage.title}`">
        <Icon name="book" :size="18" /> Read
      </a>
      <a v-if="canAssign" class="btn" :href="`#/assignments?passageId=${encodeURIComponent(passage.id)}`" :aria-label="`Assign ${passage.title}`">
        <Icon name="assign" :size="18" /> Assign
      </a>
    </div>
  </article>
</template>

<style scoped>
.pcard { display: flex; flex-direction: column; gap: 12px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: var(--s3); }
.top { display: flex; gap: 8px; flex-wrap: wrap; }
h3 { font-size: 18px; line-height: 1.3; }
.meta { display: flex; gap: var(--s3); margin: 0; }
.meta dt { font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 700; }
.meta dd { margin: 0; font-weight: 600; font-size: 18px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: auto; }
.pcard.list { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: var(--s2); padding: var(--s2) var(--s3); }
.pcard.list .top { grid-column: 1; order: 2; }
.pcard.list h3 { grid-column: 1; order: 1; }
.pcard.list .meta { grid-column: 2; grid-row: 1 / span 2; }
.pcard.list .actions { grid-column: 3; grid-row: 1 / span 2; margin-top: 0; }
@media (max-width: 720px) {
  .pcard.list { display: flex; }
}
</style>
