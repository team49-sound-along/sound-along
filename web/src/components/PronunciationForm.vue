<script setup>
import { computed, ref, watch } from "vue";
import { normalizeWord, validatePronunciation } from "../pronunciations.js";

const props = defineProps({
  presetWord: { type: String, default: "" },
  known: { type: Array, default: () => [] },
  busy: Boolean,
  error: { type: String, default: "" },
});
const emit = defineEmits(["save"]);
const word = ref(props.presetWord);
const respelling = ref("");
const touched = ref(false);
const exists = computed(() => props.known.includes(normalizeWord(word.value)));
const check = () => validatePronunciation({ word: word.value, respelling: respelling.value });
const errors = () => (touched.value ? check().errors : {});

watch(() => props.presetWord, (w) => { word.value = w; respelling.value = ""; touched.value = false; });
defineExpose({ clear: () => { word.value = ""; respelling.value = ""; touched.value = false; } });

function submit() {
  touched.value = true;
  if (check().valid) emit("save", normalizeWord(word.value), respelling.value.trim());
}
</script>

<template>
  <form class="card form" novalidate aria-labelledby="pf-h" @submit.prevent="submit">
    <h3 id="pf-h">{{ exists ? "Update a pronunciation" : "Add a pronunciation" }}</h3>
    <div class="grid">
      <div class="field">
        <label for="pf-word">Word</label>
        <input id="pf-word" v-model="word" class="input" type="text" autocomplete="off" autocapitalize="none" spellcheck="false" aria-describedby="pf-word-err" :aria-invalid="!!errors().word" />
        <span id="pf-word-err" class="error-text">{{ errors().word }}</span>
      </div>
      <div class="field">
        <label for="pf-resp">How it should sound</label>
        <input id="pf-resp" v-model="respelling" class="input" type="text" autocomplete="off" spellcheck="false" aria-describedby="pf-rules pf-resp-err" :aria-invalid="!!errors().respelling" />
        <span id="pf-resp-err" class="error-text">{{ errors().respelling }}</span>
      </div>
    </div>
    <p v-if="exists" class="small muted">This word already has a pronunciation. Saving replaces it.</p>
    <div id="pf-rules" class="rules small muted">
      <strong>Rules</strong>
      <ul>
        <li><b>Word:</b> 1 to 40 lowercase letters, apostrophes or hyphens.</li>
        <li><b>Plain respelling:</b> letters, spaces and hyphens, like <code>gay-uh-teez</code>.</li>
        <li><b>Or phonemes</b> between slashes, like <code>/ɡˈAɪtˌiz/</code>.</li>
        <li>Up to 60 characters. Applies to passages generated or regenerated from now on.</li>
      </ul>
    </div>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <div><button class="btn primary" type="submit" :disabled="busy">{{ busy ? "Saving..." : "Save pronunciation" }}</button></div>
  </form>
</template>

<style scoped>
.form { display: grid; gap: var(--s2); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); gap: var(--s2); }
.grid > * { min-width: 0; }
.rules ul { margin: 4px 0 0; padding-left: 20px; display: grid; gap: 2px; }
code { font-family: ui-monospace, Menlo, Consolas, monospace; overflow-wrap: anywhere; }
</style>
