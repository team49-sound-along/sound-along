<script setup>
// "What to do next": two or three plain suggestions, made by the rules in readAloudStory.js. Hidden when data is thin.
defineProps({ cards: { type: Array, required: true } });
</script>

<template>
  <ul class="steps" data-testid="ra-steps">
    <li v-for="c in cards" :key="c.id" class="step" :data-step="c.id">
      <strong>{{ c.title }}</strong>
      <p v-if="c.words" class="words"><span v-for="w in c.words" :key="w" class="chip">{{ w }}</span></p>
    </li>
  </ul>
</template>

<style scoped>
.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: var(--s1); }
.step { display: grid; align-content: start; gap: 6px; padding: 12px var(--s2); border-left: 6px solid var(--primary); background: var(--bg); border-radius: var(--r-sm); }
.words { margin: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.chip { padding: 2px 10px; border-radius: 999px; background: var(--heat-2); font-weight: 700; }
</style>
