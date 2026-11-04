<script setup>
// Tabs shared by the teacher's "Voice" screens: reading settings, pronunciations, words to check, and the listening test.
import { computed } from "vue";
import { route } from "../router.js";

const TABS = [
  { name: "settings", href: "#/settings", label: "Reading settings" },
  { name: "pronunciations", href: "#/pronunciations", label: "Pronunciations" },
  { name: "review", href: "#/review", label: "Words to check" },
  { name: "listening", href: "#/listening", label: "Listening test" },
];
const active = computed(() => route.value.name);
</script>

<template>
  <nav class="tabs" aria-label="Voice">
    <a v-for="t in TABS" :key="t.name" :href="t.href" :aria-current="active === t.name ? 'page' : undefined">{{ t.label }}</a>
  </nav>
</template>

<style scoped>
.tabs { display: flex; gap: 4px; flex-wrap: wrap; padding: var(--s1) var(--s3) 0; max-width: 1100px; margin: 0 auto; border-bottom: 1px solid var(--border); }
a { display: inline-flex; align-items: center; min-height: 44px; padding: 0 14px; color: var(--muted); font-weight: 600; font-size: 15px; text-decoration: none; border-radius: var(--r-sm) var(--r-sm) 0 0; }
a:hover { color: var(--text); background: var(--surface-2); }
a[aria-current="page"] { color: var(--primary); box-shadow: inset 0 -3px 0 var(--primary); }
@media (max-width: 640px) { .tabs { padding: var(--s1) var(--s2) 0; } }
</style>
