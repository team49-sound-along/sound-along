<script setup>
// Reading settings panel: text size, font, spacing, highlight and two switches. It only emits the new prefs;
// the reader owns storage. Choices are native radios, so keyboard and screen readers work without extra code.
import RadioGroup from "./RadioGroup.vue";
import SwitchControl from "./SwitchControl.vue";
import { updatePref } from "../readingPrefs.js";

const props = defineProps({ prefs: { type: Object, required: true } });
const emit = defineEmits(["change", "close"]);

const SIZE = [{ value: "large", label: "Large" }, { value: "xl", label: "Extra large" }, { value: "huge", label: "Huge" }];
const FONT = [{ value: "standard", label: "Standard" }, { value: "atkinson", label: "Atkinson" }, { value: "lexend", label: "Lexend" }];
const SPACING = [{ value: "normal", label: "Normal" }, { value: "roomy", label: "Roomy" }, { value: "extra", label: "Extra roomy" }];
const HIGHLIGHT = [{ value: "words", label: "Words" }, { value: "sentences", label: "Sentences" }, { value: "off", label: "Off" }];

const set = (key, value) => emit("change", updatePref(props.prefs, key, value));
</script>

<template>
  <section id="reading-settings" class="panel" aria-labelledby="rs-h">
    <div class="top">
      <h3 id="rs-h">Reading settings</h3>
      <button class="btn" type="button" @click="emit('close')">Done</button>
    </div>
    <div class="grid">
      <RadioGroup legend="Text size" name="rs-size" inline :options="SIZE" :model-value="prefs.size" @update:model-value="set('size', $event)" />
      <RadioGroup legend="Highlight" name="rs-highlight" inline :options="HIGHLIGHT" :model-value="prefs.highlight" @update:model-value="set('highlight', $event)" />
      <RadioGroup legend="Spacing" name="rs-spacing" inline hint="Letter and word spacing change together." :options="SPACING" :model-value="prefs.spacing" @update:model-value="set('spacing', $event)" />
      <RadioGroup legend="Font" name="rs-font" inline :options="FONT" :model-value="prefs.font" @update:model-value="set('font', $event)" />
    </div>
    <div class="switches">
      <SwitchControl label="Line breaks at phrases" show-label :model-value="prefs.phraseBreaks" @update:model-value="set('phraseBreaks', $event)" />
      <SwitchControl label="Reduce motion" show-label :model-value="prefs.reduceMotion" @update:model-value="set('reduceMotion', $event)" />
    </div>
    <p class="small muted"><strong>Reduce motion:</strong> the page never scrolls by itself and nothing fades or slides. When the word being read is off screen, a button lets you jump to it. The highlight still follows the voice; choose the Sentences highlight to move even less.</p>
    <p class="small muted">Atkinson and Lexend are fonts made to be easy to read. Choose what feels best. Your choices stay on this device.</p>
  </section>
</template>

<style scoped>
.panel { display: grid; gap: var(--s2); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: var(--s3); }
.top { display: flex; align-items: center; justify-content: space-between; gap: var(--s2); }
.top h3 { font-size: 18px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: var(--s3) var(--s3); }
.switches { display: flex; flex-wrap: wrap; gap: var(--s1) var(--s3); border-top: 1px solid var(--border); padding-top: var(--s2); }
</style>
