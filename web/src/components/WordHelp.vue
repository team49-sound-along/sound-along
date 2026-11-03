<script setup>
// Word-help panel: the vocabulary note (when Word help is on) plus the "Hear this word" control.
defineProps({
  note: { type: Object, default: null },
  showNote: Boolean,
  word: { type: String, default: "" },
  canHear: Boolean,
});
const emit = defineEmits(["hear"]);
</script>

<template>
  <div class="help" role="region" aria-label="Word help">
    <div v-if="showNote" aria-live="polite" aria-atomic="true">
      <template v-if="note">
        <div class="note-head"><strong>{{ note.word }}</strong><span v-if="note.partOfSpeech" class="badge">{{ note.partOfSpeech }}</span></div>
        <p class="note-def">{{ note.definition }}</p>
        <p v-for="e in note.examples" :key="e" class="note-extra"><span class="label">Example</span> {{ e }}</p>
        <p v-if="note.spanish.length" class="note-extra"><span class="label">En español</span> <span lang="es">{{ note.spanish.join(", ") }}</span></p>
      </template>
      <span v-else class="muted">Underlined words have a short definition. It appears here as the word is read.</span>
    </div>
    <div class="hear">
      <button
        class="btn" type="button" :disabled="!word || !canHear" :aria-disabled="!word || !canHear"
        :title="!word ? 'Tap or focus a word first' : canHear ? 'Plays just this word (shortcut: H)' : 'This word\'s timing is estimated, so it cannot be played on its own'"
        @click="emit('hear')"
      >Hear &ldquo;{{ word || "a word" }}&rdquo;</button>
      <span class="small muted" aria-live="polite">{{ !word ? "Tap or focus a word to hear it alone." : canHear ? "Plays only this word. Shortcut: H." : "Not available: this word's timing is estimated." }}</span>
    </div>
  </div>
</template>

<style scoped>
.help { position: sticky; bottom: var(--s2); z-index: 10; display: grid; gap: var(--s1); background: var(--surface); border: 1px solid var(--border); border-left: 6px solid var(--hl); border-radius: var(--r); padding: 12px var(--s2); font-size: 18px; box-shadow: 0 6px 20px rgb(0 0 0 / 0.08); min-width: 0; }
.help strong { margin-right: 8px; font-size: 20px; }
.note-head { display: flex; align-items: center; gap: 8px; }
.note-def { margin-top: 4px; }
.note-extra { margin-top: 6px; font-size: 16px; color: var(--muted); }
.note-extra .label { font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; margin-right: 6px; }
.hear { display: flex; align-items: center; gap: var(--s1) var(--s2); flex-wrap: wrap; }
.hear .btn { max-width: 100%; overflow-wrap: anywhere; }
</style>
