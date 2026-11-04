<script setup>
// "Quiz" button for the reader header: shown only when a person has approved questions for this passage (its own, its voice pair's, or the other language's).
import { onMounted, ref } from "vue";
import { loadQuiz } from "../quizLoad.js";

const props = defineProps({ passageId: { type: String, required: true }, timing: { type: Object, required: true } });
const available = ref(false);
onMounted(async () => {
  available.value = (await loadQuiz(props.passageId, props.timing)) !== null;
});
</script>

<template>
  <a v-if="available" class="btn" :href="`#/quiz/${encodeURIComponent(passageId)}`">Quiz</a>
</template>
