<script setup>
import { computed, ref, watch } from "vue";
import StateBlock from "../components/StateBlock.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import VoiceSample from "../components/VoiceSample.vue";

const voiceLabel = (list, id) => list.find((v) => v.id === id)?.label ?? "this voice";
import { DEFAULT_POLLY_QUALITY, DEFAULT_TTS_ENGINE, KBPS_OPTIONS, POLLY_QUALITY_OPTIONS, SPEED_MAX, SPEED_MIN, SPEED_STEP, TTS_ENGINE_OPTIONS, formForEngine, formatSpeed, isDirty, mbPerMinute, settingsPayload, voiceGroups, voicesForEngine } from "../settings.js";

const { data, loading, error, reload } = useResource(() => api.settings());
const form = ref({ voice: "", voiceEs: "", speed: 0.95, mp3Kbps: 48, ttsEngine: DEFAULT_TTS_ENGINE, pollyEngine: DEFAULT_POLLY_QUALITY });
const usesPolly = computed(() => form.value.ttsEngine === "polly");
const saving = ref(false);
const saveError = ref("");
const saved = ref("");

watch(data, (d) => { if (d) form.value = { voice: d.voice, voiceEs: d.voiceEs ?? "", speed: d.speed, mp3Kbps: d.mp3Kbps, ttsEngine: d.ttsEngine ?? DEFAULT_TTS_ENGINE, pollyEngine: d.pollyEngine ?? DEFAULT_POLLY_QUALITY }; }, { immediate: true });
const dirty = computed(() => isDirty(data.value, form.value));
const enVoices = computed(() => voicesForEngine(data.value?.voices, form.value.ttsEngine, "en"));
const esVoices = computed(() => voicesForEngine(data.value?.voices, form.value.ttsEngine, "es"));
const enGroups = computed(() => voiceGroups(enVoices.value, form.value.ttsEngine));
const esGroups = computed(() => voiceGroups(esVoices.value, form.value.ttsEngine));
const engineOf = (list, id) => list.find((v) => v.id === id)?.engine ?? "";
// Choosing an engine swaps the voice menus; a voice the other engine does not offer becomes that engine's default.
const chooseEngine = (engine) => { form.value = formForEngine(form.value, engine, data.value?.voices, data.value?.voiceDefaults); };
const size = computed(() => mbPerMinute(Number(form.value.mp3Kbps)));

async function save() {
  saving.value = true;
  saveError.value = "";
  saved.value = "";
  try {
    data.value = await api.saveSettings(settingsPayload(form.value));
    saved.value = "Settings saved. They apply to passages generated or regenerated from now on.";
  } catch (e) {
    saveError.value = e.message;
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="page narrow">
    <div class="page-head">
      <div>
        <h2>Voice settings</h2>
        <p>Choose how new narration sounds. Changes apply to passages generated or regenerated from now on. Passages already made keep the settings they were made with.</p>
      </div>
    </div>
    <StateBlock :loading="loading" :error="error" loading-label="Loading settings" @retry="reload">
      <form v-if="data" class="card form" novalidate @submit.prevent="save">
        <fieldset class="field engines">
          <legend>Narration engine</legend>
          <label v-for="e in TTS_ENGINE_OPTIONS" :key="e.id" class="engine" :class="{ on: form.ttsEngine === e.id }">
            <input v-model="form.ttsEngine" type="radio" name="s-engine" :value="e.id" :aria-describedby="`s-engine-${e.id}`" @change="chooseEngine(e.id)" />
            <span>
              <strong>{{ e.label }}</strong>
              <span :id="`s-engine-${e.id}`" class="small muted">{{ e.hint }}</span>
            </span>
          </label>
        </fieldset>
        <div class="field">
          <label for="s-voice">English voice</label>
          <div class="pickrow">
            <select id="s-voice" v-model="form.voice" class="input" aria-describedby="s-voice-help">
              <optgroup v-for="g in enGroups" :key="g.label" :label="g.label">
                <option v-for="v in g.voices" :key="v.id" :value="v.id">{{ v.label }}</option>
              </optgroup>
            </select>
            <VoiceSample :voice="form.voice" :engine="engineOf(enVoices, form.voice)" :label="voiceLabel(enVoices, form.voice)" autoplay />
          </div>
          <p id="s-voice-help" class="small muted">Choosing a voice plays a short sample. Press Hear it to play it again.</p>
        </div>
        <div v-if="esVoices.length" class="field">
          <label for="s-voice-es">Spanish voice</label>
          <div class="pickrow">
            <select id="s-voice-es" v-model="form.voiceEs" class="input">
              <optgroup v-for="g in esGroups" :key="g.label" :label="g.label">
                <option v-for="v in g.voices" :key="v.id" :value="v.id">{{ v.label }}</option>
              </optgroup>
            </select>
            <VoiceSample :voice="form.voiceEs" :engine="engineOf(esVoices, form.voiceEs)" :label="voiceLabel(esVoices, form.voiceEs)" autoplay />
          </div>
        </div>
        <fieldset v-if="usesPolly" class="field engines" data-testid="polly-quality">
          <legend>Voice quality</legend>
          <label v-for="q in POLLY_QUALITY_OPTIONS" :key="q.id" class="engine" :class="{ on: form.pollyEngine === q.id }">
            <input v-model="form.pollyEngine" type="radio" name="s-quality" :value="q.id" :aria-describedby="`s-quality-${q.id}`" />
            <span>
              <strong>{{ q.label }}</strong>
              <span :id="`s-quality-${q.id}`" class="small muted">{{ q.hint }}</span>
            </span>
          </label>
        </fieldset>
        <div class="field">
          <label for="s-speed">Speaking speed: <span class="num value">{{ formatSpeed(form.speed) }}</span></label>
          <input id="s-speed" v-model.number="form.speed" class="range" type="range" :min="SPEED_MIN" :max="SPEED_MAX" :step="SPEED_STEP" aria-describedby="s-speed-help" :aria-valuetext="formatSpeed(form.speed)" />
          <div class="ends small muted" aria-hidden="true"><span>{{ SPEED_MIN }}x slower</span><span>{{ SPEED_MAX }}x faster</span></div>
          <p id="s-speed-help" class="small muted">Slower speech helps younger readers follow each word. Faster speech suits confident readers. The speed does not change Hadley, Everly, Bryony or Trevor; readers can still change the speed while they read.</p>
        </div>
        <div class="field">
          <label for="s-kbps">MP3 quality</label>
          <select id="s-kbps" v-model.number="form.mp3Kbps" class="input" aria-describedby="s-kbps-help">
            <option v-for="k in KBPS_OPTIONS" :key="k" :value="k">{{ k }} kbps</option>
          </select>
          <p id="s-kbps-help" class="small muted">Lower bitrate means a smaller file: about {{ size }} MB per minute of narration at {{ form.mp3Kbps }} kbps. Smaller files load faster on slow connections and cost less to deliver over time, especially for long passages used by many students. Speech stays clear at 48 kbps.</p>
        </div>
        <p class="sr-only" role="status" aria-live="polite">{{ saved }}</p>
        <p v-if="saved" class="notice ok">{{ saved }}</p>
        <p v-if="saveError" class="notice error" role="alert">{{ saveError }}</p>
        <div><button class="btn primary" type="submit" :disabled="saving || !dirty">{{ saving ? "Saving..." : "Save settings" }}</button></div>
      </form>
    </StateBlock>
  </div>
</template>

<style scoped>
@media (min-width: 521px) { #s-kbps { width: calc(100% - 120px); } } /* same width as the voice dropdowns, which share their row with Hear it */
.pickrow { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pickrow .input { flex: 1 1 260px; min-width: 0; }
.form { display: grid; gap: var(--s3); }
.value { font-weight: 700; color: var(--primary); }
.range { width: 100%; min-height: 44px; accent-color: var(--primary); margin: 0; }
.ends { display: flex; justify-content: space-between; gap: var(--s1); }
.engines { border: 0; margin: 0; padding: 0; display: grid; gap: 8px; }
.engines legend { font-weight: 600; margin-bottom: 4px; padding: 0; }
.engine { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; min-height: 44px; border: 1px solid var(--border, #d0d5dd); border-radius: 8px; cursor: pointer; }
.engine.on { border-color: var(--primary); box-shadow: inset 0 0 0 1px var(--primary); }
.engine input { margin-top: 3px; accent-color: var(--primary); }
.engine > span { display: grid; gap: 2px; }
</style>
