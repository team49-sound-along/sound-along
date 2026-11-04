<script setup>
import { computed, ref, watch } from "vue";
import StateBlock from "../components/StateBlock.vue";
import { api } from "../api.js";
import { useResource } from "../useResource.js";
import { voicesFor } from "../language.js";
import VoiceSample from "../components/VoiceSample.vue";

const voiceLabel = (list, id) => list.find((v) => v.id === id)?.label ?? "this voice";
import { KBPS_OPTIONS, SPEED_MAX, SPEED_MIN, SPEED_STEP, formatSpeed, isDirty, mbPerMinute, settingsPayload } from "../settings.js";

const { data, loading, error, reload } = useResource(() => api.settings());
const form = ref({ voice: "", voiceEs: "", speed: 0.95, mp3Kbps: 48 });
const saving = ref(false);
const saveError = ref("");
const saved = ref("");

watch(data, (d) => { if (d) form.value = { voice: d.voice, voiceEs: d.voiceEs ?? "", speed: d.speed, mp3Kbps: d.mp3Kbps }; }, { immediate: true });
const dirty = computed(() => isDirty(data.value, form.value));
const enVoices = computed(() => voicesFor(data.value?.voices, "en"));
const esVoices = computed(() => voicesFor(data.value?.voices, "es"));
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
        <div class="field">
          <label for="s-voice">English voice</label>
          <div class="pickrow">
            <select id="s-voice" v-model="form.voice" class="input" aria-describedby="s-voice-help">
              <optgroup label="Recommended (passed our listening test)">
                <option v-for="v in enVoices.filter((x) => x.recommended !== false)" :key="v.id" :value="v.id">{{ v.label }}</option>
              </optgroup>
              <optgroup v-if="enVoices.some((x) => x.recommended === false)" label="More voices to try (less natural)">
                <option v-for="v in enVoices.filter((x) => x.recommended === false)" :key="v.id" :value="v.id">{{ v.label }}</option>
              </optgroup>
            </select>
            <VoiceSample :voice="form.voice" :label="voiceLabel(enVoices, form.voice)" autoplay />
          </div>
          <p id="s-voice-help" class="small muted">Choosing a voice plays a short sample. Press Hear it to play it again.</p>
        </div>
        <div v-if="esVoices.length" class="field">
          <label for="s-voice-es">Spanish voice</label>
          <div class="pickrow">
            <select id="s-voice-es" v-model="form.voiceEs" class="input">
              <option v-for="v in esVoices" :key="v.id" :value="v.id">{{ v.label }}</option>
            </select>
            <VoiceSample :voice="form.voiceEs" :label="voiceLabel(esVoices, form.voiceEs)" autoplay />
          </div>
        </div>
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
.pickrow { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.pickrow .input { flex: 1 1 260px; min-width: 0; }
.form { display: grid; gap: var(--s3); }
.value { font-weight: 700; color: var(--primary); }
.range { width: 100%; min-height: 44px; accent-color: var(--primary); margin: 0; }
.ends { display: flex; justify-content: space-between; gap: var(--s1); }
</style>
