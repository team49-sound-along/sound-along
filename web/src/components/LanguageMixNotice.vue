<script setup>
// Shown when the text is a real mix of English and Spanish: one voice reads one language, so the teacher chooses which paragraphs to keep.
defineProps({ mix: { type: Object, required: true }, canUndo: Boolean });
const emit = defineEmits(["keep", "undo"]);
const NAME = { en: "English", es: "Spanish" };
</script>

<template>
  <div v-if="mix.mixed || canUndo" class="notice mixed" role="status">
    <template v-if="mix.mixed">
      <p>
        <strong>This text mixes English and Spanish.</strong> A voice reads one language at a time. About {{ mix.words.en }} words look English and {{ mix.words.es }} look Spanish.
      </p>
      <div class="row">
        <button type="button" class="btn" @click="emit('keep', 'es')">Keep only the Spanish paragraphs</button>
        <button type="button" class="btn" @click="emit('keep', 'en')">Keep only the English paragraphs</button>
      </div>
    </template>
    <p v-if="canUndo" class="small">
      Paragraphs in the other language were removed. <button type="button" class="linklike" @click="emit('undo')">Undo</button>
    </p>
  </div>
</template>

<style scoped>
.mixed { display: grid; gap: var(--s1); }
.row { display: flex; gap: var(--s1); flex-wrap: wrap; }
.linklike { background: none; border: 0; padding: 0; color: var(--primary); text-decoration: underline; cursor: pointer; font: inherit; min-height: 32px; }
</style>
