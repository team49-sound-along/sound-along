<script setup>
// Word card: shown for the word the reader tapped or focused. It never opens by itself while audio plays
// (interactive extras that interrupt reading distracted young readers in the research). Shows a place card
// when the tapped word is part of a named place. Fields are optional: a card from the passage vocabulary has no IPA.
defineProps({
  card: { type: Object, default: null },
  place: { type: Object, default: null },
  showNote: Boolean,
  word: { type: String, default: "" },
  canHear: Boolean,
  starred: Boolean,
});
const emit = defineEmits(["hear", "star"]);
</script>

<template>
  <div class="help" role="region" aria-label="Word help">
    <div v-if="showNote" aria-live="polite" aria-atomic="true" class="cards">
      <article v-if="card" class="card-body" aria-label="Word card">
        <div class="head">
          <strong class="w">{{ card.word }}</strong>
          <span v-if="card.partOfSpeech" class="badge">{{ card.partOfSpeech }}</span>
        </div>
        <figure v-if="card.imageUrl" :key="card.imageUrl" class="wpic">
          <img
            :src="card.imageUrl" :alt="card.imageAlt || ''" :width="card.imageWidth || undefined" :height="card.imageHeight || undefined"
            decoding="async" @error="$event.target.closest('figure').hidden = true"
          />
          <figcaption v-if="card.imageCredit">{{ card.imageCredit }}</figcaption>
        </figure>
        <p v-if="card.syllables || card.ipa" class="say muted">
          <span v-if="card.syllables">{{ card.syllables }}</span>
          <span v-if="card.syllables && card.ipa" aria-hidden="true"> &middot; </span>
          <span v-if="card.ipa"><span class="sr-only">Pronounced </span>{{ card.ipa }}</span>
        </p>
        <p v-if="card.definition" class="def">{{ card.definition }}</p>
        <p v-if="card.example" class="extra"><span class="label">Example</span> {{ card.example }}</p>
        <p v-if="card.translation?.words?.length" class="extra"><span class="label">{{ card.translation.lang === "es" ? "En español" : "In English" }}</span> <span :lang="card.translation.lang">{{ card.translation.words.join(", ") }}</span></p>
        <p v-if="card.spanish?.length" class="extra"><span class="label">En español</span> <span lang="es">{{ card.spanish.join(", ") }}</span></p>
      </article>
      <article v-if="place" class="card-body place" aria-label="Place card">
        <div class="head"><strong class="w">{{ place.name }}</strong><span class="badge">Place</span></div>
        <figure v-if="place.imageUrl" :key="place.imageUrl" class="pic">
          <img
            :src="place.imageUrl" :alt="place.imageAlt || ''" :width="place.imageWidth || undefined" :height="place.imageHeight || undefined"
            decoding="async" @error="$event.target.closest('figure').hidden = true"
          />
          <figcaption v-if="place.imageCredit">{{ place.imageCredit }}</figcaption>
        </figure>
        <figure v-else class="pic nopic" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="40" height="40" focusable="false"><path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z"/></svg>
        </figure>
        <p class="def">{{ place.summary }}</p>
        <p v-if="place.attribution" class="extra">{{ place.attribution }}</p>
      </article>
      <p v-if="card || word" class="save"><button type="button" class="btn" :aria-pressed="starred" @click="emit('star')">{{ starred ? "&#9733; Saved to My words" : "&#9734; Save word" }}</button></p>
      <p v-if="!card && !place && !word" class="muted intro">Tap a word to hear it from there. Underlined words have a short definition.</p>
      <p v-else-if="!card && !place" class="muted">No definition for this word yet. You can still hear it and save it to practice.</p>
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
.help { display: grid; gap: var(--s2); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: var(--s3); font-size: 18px; min-width: 0; }
.cards { display: grid; gap: var(--s2); }
.head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.w { font-size: 24px; margin-right: 4px; }
.say { margin-top: 2px; font-size: 16px; }
.def { margin-top: 6px; }
.extra { margin-top: 6px; font-size: 16px; color: var(--muted); }
.extra .label { font-size: 12px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; margin-right: 6px; }
.place { border-top: 1px solid var(--border); padding-top: var(--s2); }
.pic { margin: 8px 0 0; }
.pic[hidden] { display: none; }
.pic img { display: block; width: 100%; height: auto; max-height: 280px; object-fit: contain; border-radius: 12px; background: var(--border); }
.nopic { display: grid; place-items: center; height: 72px; border-radius: 12px; background: var(--border); color: var(--muted); }
.pic figcaption { margin-top: 4px; font-size: 12px; color: var(--muted); }
.wpic { margin: 8px 0 0; }
.wpic[hidden] { display: none; }
.wpic img { display: block; width: auto; max-width: 100%; height: auto; max-height: 200px; border-radius: 12px; background: var(--border); }
.wpic figcaption { margin-top: 4px; font-size: 12px; color: var(--muted); }
.hear { display: flex; align-items: center; gap: var(--s1) var(--s2); flex-wrap: wrap; }
.hear .btn { max-width: 100%; overflow-wrap: anywhere; }
@media (max-width: 520px) { .intro { display: none; } }
</style>
