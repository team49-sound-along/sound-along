<script setup>
// Main navigation in the top bar: every destination is visible, nothing is hidden under a menu.
// Teacher: Library, Assignments, Create, Insights, Voice (voice settings, pronunciations, words to check, listening test).
// Student: Library, My assignments, Create, My words. On a phone the list opens as one panel from the menu button in App.vue.
import { computed } from "vue";
import { VOICE_SECTION, route } from "../router.js";
import { role } from "../session.js";

defineProps({ open: Boolean });
const emit = defineEmits(["navigate"]);

const items = computed(() =>
  role.value === "student"
    ? [
        { name: "library", href: "#/library", label: "Library" },
        { name: "assignments", href: "#/assignments", label: "My assignments" },
        { name: "generate", href: "#/generate", label: "Create" },
        { name: "words", href: "#/words", label: "My words" },
      ]
    : [
        { name: "library", href: "#/library", label: "Library" },
        { name: "assignments", href: "#/assignments", label: "Assignments" },
        { name: "generate", href: "#/generate", label: "Create" },
        { name: "insights", href: "#/insights", label: "Insights" },
        { name: "voice", href: "#/settings", label: "Voice" },
      ],
);
const activeName = computed(() => {
  const n = route.value.name;
  if (n === "read") return "library";
  if (n === "practice") return role.value === "student" ? "words" : "library";
  if (VOICE_SECTION.includes(n) && role.value === "teacher") return "voice";
  return n;
});
</script>

<template>
  <nav aria-label="Main" class="nav" :class="{ open }">
    <ul>
      <li v-for="i in items" :key="i.name">
        <a :href="i.href" :aria-current="activeName === i.name ? 'page' : undefined" @click="emit('navigate')">{{ i.label }}</a>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
.nav { display: flex; align-items: center; }
ul { list-style: none; margin: 0; padding: 0; display: flex; gap: var(--s1); }
a { display: inline-flex; align-items: center; min-height: 44px; padding: 0 14px; border-radius: var(--r-sm); color: var(--muted); font-weight: 600; font-size: 15px; text-decoration: none; }
a:hover { color: var(--text); background: var(--surface-2); }
a[aria-current="page"] { color: var(--primary); box-shadow: inset 0 -3px 0 var(--primary); border-radius: 0; }

@media (max-width: 860px) {
  .nav { display: none; position: fixed; top: var(--topbar-h); left: 0; right: 0; z-index: 25; flex-direction: column; align-items: stretch; padding: var(--s1) var(--s2) var(--s2); background: var(--surface); border-bottom: 1px solid var(--border); box-shadow: 0 12px 24px rgb(31 42 48 / 0.12); }
  .nav.open { display: flex; }
  ul { flex-direction: column; }
  a[aria-current="page"] { box-shadow: inset 3px 0 0 var(--primary); background: var(--primary-soft); border-radius: var(--r-sm); }
}
</style>
