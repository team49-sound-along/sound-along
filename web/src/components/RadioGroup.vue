<script setup>
// Accessible native radio group in a fieldset. Options: [{ value, label }].
defineProps({
  legend: { type: String, required: true },
  name: { type: String, required: true },
  options: { type: Array, required: true },
  modelValue: { default: null },
  hint: { type: String, default: "" },
  disabled: Boolean,
  inline: Boolean,
});
const emit = defineEmits(["update:modelValue"]);
</script>

<template>
  <fieldset class="rg" :disabled="disabled">
    <legend>{{ legend }}</legend>
    <p v-if="hint" class="small muted hint">{{ hint }}</p>
    <div class="opts" :class="{ inline }">
      <label v-for="o in options" :key="o.value" class="opt" :class="{ on: modelValue === o.value }">
        <input type="radio" :name="name" :value="o.value" :checked="modelValue === o.value" @change="emit('update:modelValue', o.value)" />
        <span>{{ o.label }}</span>
      </label>
    </div>
  </fieldset>
</template>

<style scoped>
.rg { border: 0; margin: 0; padding: 0; min-width: 0; display: grid; gap: 8px; }
legend { font-size: 14px; font-weight: 600; padding: 0; margin-bottom: 4px; }
.hint { margin: 0; }
.opts { display: flex; flex-wrap: wrap; gap: 8px; min-width: 0; }
.opt { display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 44px; min-width: 44px; padding: 0 14px; border: 1px solid var(--muted); border-radius: var(--r-sm); background: var(--surface); cursor: pointer; font-weight: 600; }
.opt input { width: 20px; height: 20px; margin: 0; accent-color: var(--primary); }
.opt:hover { background: var(--surface-2); }
.opt.on { background: var(--primary-soft); border-color: var(--primary); color: var(--primary); }
.opt:has(input:focus-visible) { outline: 3px solid var(--focus); outline-offset: 2px; }
</style>
