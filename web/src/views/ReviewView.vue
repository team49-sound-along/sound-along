<script setup>
import { ref, watch } from "vue";
import StateBlock from "../components/StateBlock.vue";
import ReviewPassage from "../components/ReviewPassage.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import { dismissWord, suspectCount } from "../review.js";

const { data, loading, error, reload } = useResource(() => api.review());
const items = ref([]);
watch(data, (d) => { if (d) items.value = d; });
const actionError = ref("");

// Optimistic: remove first, restore the list if the server refuses. No undo.
async function dismiss(word) {
  const before = items.value;
  items.value = dismissWord(before, word);
  actionError.value = "";
  try {
    await api.dismissReview(word);
  } catch (e) {
    items.value = before;
    actionError.value = `Could not dismiss "${word}". ${e.message}`;
  }
}
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2>Pronunciation review</h2>
        <p>Words an automatic check thinks the voice may have said differently from the text.</p>
      </div>
      <a class="btn" href="#/pronunciations">Pronunciations</a>
    </div>

    <div class="notice warn honesty" role="note">
      <ul>
        <li>These are <strong>candidates</strong> from an automatic speech-recognition check, not confirmed mistakes.</li>
        <li>Many are only spelling differences, for example British and American (colour and color), and can be dismissed.</li>
        <li>The check only runs for passages generated here, not the built-in sample passages.</li>
        <li><strong>Listening is the real test.</strong> Open the passage and listen before you change anything.</li>
      </ul>
    </div>

    <p v-if="actionError" class="notice error" role="alert">{{ actionError }}</p>
    <StateBlock :loading="loading" :error="error" :empty="!loading && !error && !items.length" empty-title="Nothing to review" empty-text="No suspect words right now. Generate a passage and any candidates will appear here." loading-label="Loading review" @retry="reload">
      <p class="small muted" role="status">{{ suspectCount(items) }} candidate{{ suspectCount(items) === 1 ? "" : "s" }} in {{ items.length }} passage{{ items.length === 1 ? "" : "s" }}.</p>
      <ReviewPassage v-for="it in items" :key="it.passageId" :item="it" @dismiss="dismiss" />
    </StateBlock>
  </div>
</template>

<style scoped>
.honesty ul { margin: 0; padding-left: 20px; display: grid; gap: 4px; }
</style>
