<script setup>
defineProps({ modelValue: Boolean, label: { type: String, required: true }, busy: Boolean, showLabel: Boolean });
const emit = defineEmits(["update:modelValue"]);
</script>

<template>
  <button class="sw" type="button" role="switch" :aria-checked="modelValue" :aria-label="showLabel ? undefined : label" :disabled="busy" @click="emit('update:modelValue', !modelValue)">
    <span class="track" aria-hidden="true"><span class="knob"></span></span>
    <span v-if="showLabel">{{ label }}</span>
    <span v-else class="sr-only">{{ modelValue ? "On" : "Off" }}</span>
  </button>
</template>

<style scoped>
.sw { display: inline-flex; align-items: center; gap: 10px; min-height: 44px; min-width: 48px; padding: 0 4px; border: 0; background: transparent; font-weight: 600; cursor: pointer; }
.sw[disabled] { opacity: 0.6; cursor: progress; }
.track { width: 44px; height: 26px; border-radius: 13px; background: var(--muted); position: relative; flex: none; transition: background 0.15s; }
.knob { position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%; background: var(--surface); transition: transform 0.15s; }
.sw[aria-checked="true"] .track { background: var(--primary); }
.sw[aria-checked="true"] .knob { transform: translateX(18px); }
</style>
