<script setup>
// Question 2, "Which words are hard?": the passage text itself, shaded where students stumble. Shaded words can be tapped, hovered or
// reached with the keyboard to see "Missed by 6 of 14 readers". The hardest words also get bold and a thick underline, and a ranked list
// repeats them in words, so nothing depends on colour alone.
import { computed, ref } from "vue";
import { annotateTokens, missedText, topWordRows, wordKey } from "../heatMap.js";

const props = defineProps({ passage: { type: Object, required: true }, words: { type: Array, default: () => [] } });
const selected = ref(null);
const paragraphs = computed(() => annotateTokens(props.passage.tokens, props.passage.sessions, new Set(topWordRows(props.words).map((r) => wordKey(r.word)))));
const detail = computed(() => {
  const hit = props.passage.tokens.find((t) => t.i === selected.value);
  return hit ? `“${hit.text.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "")}”: ${missedText(hit.missed, props.passage.sessions)}` : "Tap or hover a shaded word to see how many readers missed it.";
});
</script>

<template>
  <div class="heat">
    <div class="legend small" aria-hidden="true">
      <span class="scale"><i class="s l1"></i><i class="s l2"></i><i class="s l3"></i></span>
      <span>Darker = more students stumbled here. Bold underline = hardest.</span>
    </div>

    <div class="text" data-testid="ra-heat">
      <p v-for="(words, p) in paragraphs" :key="p">
        <template v-for="w in words" :key="w.i">
          <button
            v-if="w.level > 0"
            type="button"
            class="w"
            :class="[`l${w.level}`, { top: w.top, sel: selected === w.i }]"
            :aria-label="`${w.text}, ${w.title}`"
            :aria-pressed="selected === w.i"
            @click="selected = w.i"
            @focus="selected = w.i"
            @mouseenter="selected = w.i"
          >{{ w.text }}</button>
          <span v-else>{{ w.text }}</span>{{ " " }}
        </template>
      </p>
    </div>
    <p class="detail" role="status" aria-live="polite" data-testid="ra-heat-detail">{{ detail }}</p>
  </div>
</template>

<style scoped>
.heat { display: grid; gap: var(--s2); min-width: 0; }
.legend { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s1); }
.scale { display: inline-flex; border-radius: 6px; overflow: hidden; border: 1px solid var(--border); }
.s { display: block; width: 28px; height: 16px; }
.l1 { background: var(--heat-1); }
.l2 { background: var(--heat-2); }
.l3 { background: var(--heat-3); }
.text { font-family: var(--read); font-size: 19px; line-height: 2.1; padding: var(--s2); background: var(--bg); border: 1px solid var(--border); border-radius: var(--r); display: grid; gap: var(--s2); overflow-wrap: anywhere; }
.text p { margin: 0; }
.w { font: inherit; color: var(--text); border: 0; border-radius: 6px; padding: 3px 5px; margin: 0 -1px; cursor: pointer; }
.w.top { font-weight: 700; text-decoration: underline; text-decoration-thickness: 3px; text-underline-offset: 5px; }
.w.sel { outline: 3px solid var(--primary); outline-offset: 1px; }
.detail { min-height: 28px; font-weight: 600; }
</style>
