<script setup>
// "Words to practice" in the read-aloud summary: the words that were skipped or heard differently, with one button to add them all to
// My words (the Practice flashcards). Saved on this device only (practice.js); nothing is sent anywhere.
import { computed, nextTick, ref } from "vue";
import { wordsToPractice, addAllToMyWords, countNew } from "../practiceWords.js";
import { loadState, saveState } from "../practice.js";
import { langAttr } from "../language.js";

const props = defineProps({
  follower: { type: Object, required: true },
  words: { type: Array, required: true },
  passageId: { type: String, required: true },
  language: { type: String, default: "en" },
});
const emit = defineEmits(["practice"]);

const state = ref(loadState(props.passageId));
const note = ref("");
const noteEl = ref(null);
const list = computed(() => wordsToPractice(props.follower, props.words));
const fresh = computed(() => countNew(state.value, list.value));

function addAll() {
  const next = addAllToMyWords(state.value, list.value, Date.now());
  const added = fresh.value;
  state.value = next;
  saveState(props.passageId, next);
  note.value = `${added} ${added === 1 ? "word was" : "words were"} added to My words. You can practise them in Practice.`;
  emit("practice");
  nextTick(() => noteEl.value?.focus()); // the button is replaced by this note, so keep keyboard focus here
}
</script>

<template>
  <section v-if="list.length" class="practice" aria-labelledby="pw-h">
    <h4 id="pw-h">Words to practice</h4>
    <ul class="chips" :lang="langAttr(language)">
      <li v-for="w in list" :key="w.key">{{ w.text }}<span v-if="state.words[w.key]" class="sr-only"> (in My words)</span><span v-if="state.words[w.key]" aria-hidden="true"> &#9733;</span></li>
    </ul>
    <button v-if="fresh > 0" type="button" class="btn" @click="addAll">Add {{ fresh === 1 ? "this word" : `all ${fresh}` }} to My words</button>
    <p v-else-if="!note" class="small muted">All of these are in My words.</p>
    <p v-if="note" ref="noteEl" tabindex="-1" class="small" role="status">{{ note }}</p>
  </section>
</template>

<style scoped>
.practice { display: grid; gap: var(--s1); justify-items: start; }
.practice h4 { margin: 0; font-size: 18px; }
.chips { display: flex; flex-wrap: wrap; gap: var(--s1); list-style: none; margin: 0; padding: 0; }
.chips li { padding: 4px 12px; border-radius: 999px; background: var(--primary-soft); font-family: var(--read); font-size: 18px; font-weight: 700; }
</style>
