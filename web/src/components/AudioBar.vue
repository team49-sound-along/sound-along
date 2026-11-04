<script setup>
import Icon from "./Icon.vue";
import { formatDuration } from "../format.js";

defineProps({
  playing: Boolean,
  currentMs: { type: Number, default: 0 },
  durationMs: { type: Number, default: 0 },
  speed: { type: Number, default: 1 },
  wordHelp: Boolean,
});
const emit = defineEmits(["toggle", "seek", "speed", "skip", "update:wordHelp"]);
const SPEEDS = [0.75, 1, 1.25, 1.5];
</script>

<template>
  <div class="bar" role="group" aria-label="Audio controls">
    <button class="btn step" type="button" aria-label="Back one sentence" @click="emit('skip', -1)"><Icon name="skipBack" :size="20" /></button>
    <button class="btn primary play" type="button" :aria-label="playing ? 'Pause audio and highlight' : 'Play'" @click="emit('toggle')">
      <Icon :name="playing ? 'pause' : 'play'" :size="22" />
    </button>
    <button class="btn step" type="button" aria-label="Forward one sentence" @click="emit('skip', 1)"><Icon name="skipForward" :size="20" /></button>
    <div class="scrub">
      <label class="sr-only" for="scrub">Position in passage</label>
      <input
        id="scrub" type="range" min="0" :max="durationMs" step="100" :value="currentMs"
        :style="{ '--p': durationMs ? (currentMs / durationMs) * 100 + '%' : '0%' }"
        :aria-valuetext="`${formatDuration(currentMs)} of ${formatDuration(durationMs)}`"
        @input="emit('seek', Number($event.target.value))"
      />
      <span class="time num" aria-hidden="true">{{ formatDuration(currentMs) }} / {{ formatDuration(durationMs) }}</span>
    </div>
    <div class="speeds" role="group" aria-label="Playback speed">
      <button v-for="s in SPEEDS" :key="s" type="button" :aria-pressed="speed === s" @click="emit('speed', s)">{{ s }}&times;</button>
    </div>
    <button class="toggle" type="button" role="switch" :aria-checked="wordHelp" @click="emit('update:wordHelp', !wordHelp)">
      <span class="track" aria-hidden="true"><span class="knob"></span></span>
      Word help
    </button>
  </div>
</template>

<style scoped>
.bar { display: flex; align-items: center; gap: var(--s2); flex-wrap: wrap; padding: 12px var(--s2); background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); }
.play { width: 56px; height: 56px; border-radius: 50%; padding: 0; }
.step { width: 44px; height: 44px; border-radius: 50%; padding: 0; }
.scrub { flex: 1 1 220px; min-width: 0; display: grid; gap: 2px; }
.time { font-size: 13px; color: var(--muted); }
input[type="range"] { width: 100%; height: 44px; margin: 0; background: transparent; -webkit-appearance: none; appearance: none; cursor: pointer; }
input[type="range"]::-webkit-slider-runnable-track { height: 6px; border-radius: 3px; background: linear-gradient(to right, var(--primary) var(--p), var(--border) var(--p)); }
input[type="range"]::-moz-range-track { height: 6px; border-radius: 3px; background: var(--border); }
input[type="range"]::-moz-range-progress { height: 6px; border-radius: 3px; background: var(--primary); }
input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; width: 20px; height: 20px; margin-top: -7px; border-radius: 50%; background: var(--primary); border: 3px solid var(--surface); box-shadow: 0 0 0 1px var(--primary); }
input[type="range"]::-moz-range-thumb { width: 14px; height: 14px; border-radius: 50%; background: var(--primary); border: 3px solid var(--surface); }
.speeds { flex: 0 0 auto; display: inline-flex; border: 1px solid var(--border); border-radius: var(--r-sm); overflow: hidden; }
.speeds button { min-height: 44px; min-width: 48px; border: 0; border-right: 1px solid var(--border); background: transparent; font-weight: 600; font-size: 14px; cursor: pointer; color: var(--muted); }
.speeds button:last-child { border-right: 0; }
.speeds button[aria-pressed="true"] { background: var(--primary-soft); color: var(--primary); }
.toggle { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; padding: 0 4px; border: 0; background: transparent; font-weight: 600; cursor: pointer; }
.track { width: 40px; height: 24px; border-radius: 12px; background: var(--muted); position: relative; transition: background 0.15s; }
.knob { position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 50%; background: var(--surface); transition: transform 0.15s; }
.toggle[aria-checked="true"] .track { background: var(--primary); }
.toggle[aria-checked="true"] .knob { transform: translateX(16px); }
/* A small phone: controls, position and speed fit in about 170px, so the passage keeps most of the screen. */
@media (max-width: 520px) {
  .bar { gap: 8px; padding: 8px var(--s2); }
  .scrub { flex: 1 1 120px; }
  .time { font-size: 12px; }
  input[type="range"] { height: 32px; }
  .speeds { flex: 1 1 100%; }
  .speeds button { flex: 1; min-height: 40px; min-width: 0; }
  .toggle { min-height: 40px; }
}
</style>
