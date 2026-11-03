<script setup>
import { role, setRole } from "../session.js";
const OPTIONS = [
  { value: "teacher", label: "Teacher" },
  { value: "student", label: "Student" },
];
</script>

<template>
  <div class="seg" role="radiogroup" aria-label="View as">
    <button
      v-for="o in OPTIONS"
      :key="o.value"
      type="button"
      role="radio"
      :aria-checked="role === o.value"
      :class="{ on: role === o.value }"
      @click="setRole(o.value)"
    >{{ o.label }}</button>
  </div>
</template>

<style scoped>
.seg { display: inline-flex; padding: 3px; border: 1px solid var(--border); border-radius: var(--r-sm); background: var(--surface-2); }
button { min-height: 44px; min-width: 44px; padding: 0 14px; border: 0; border-radius: 8px; background: transparent; font-weight: 600; color: var(--muted); cursor: pointer; }
button.on { background: var(--primary); color: var(--on-primary); }
</style>
