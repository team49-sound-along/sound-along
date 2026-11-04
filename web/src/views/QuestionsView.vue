<script setup>
// Teacher: question drafts waiting for a person (#/questions), and one passage's draft (#/questions/<id>).
import QuestionDraftList from "../components/QuestionDraftList.vue";
import QuestionReview from "../components/QuestionReview.vue";
import { route } from "../router.js";

const id = route.value.params.id ?? null;
</script>

<template>
  <QuestionReview v-if="id" :passage-id="id" />
  <QuestionDraftList v-else />
</template>
