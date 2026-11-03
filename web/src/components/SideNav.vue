<script setup>
import Icon from "./Icon.vue";
import { route } from "../router.js";
import { role } from "../session.js";
import { computed } from "vue";

const emit = defineEmits(["navigate"]);
const teacherItems = [
  { name: "settings", href: "#/settings", label: "Settings", icon: "settings" },
  { name: "pronunciations", href: "#/pronunciations", label: "Pronunciations", icon: "speak" },
  { name: "review", href: "#/review", label: "Pronunciation review", icon: "review" },
];
const items = computed(() => [
  { name: "library", href: "#/library", label: "Library", icon: "library" },
  { name: "assignments", href: "#/assignments", label: role.value === "student" ? "My assignments" : "Assignments", icon: "assign" },
  { name: "generate", href: "#/generate", label: "Generate", icon: "generate" },
  { name: "insights", href: "#/insights", label: "Insights", icon: "insights" },
  ...(role.value === "teacher" ? teacherItems : []),
]);
const activeName = computed(() => (route.value.name === "read" ? "library" : route.value.name));
</script>

<template>
  <nav aria-label="Main">
    <ul>
      <li v-for="i in items" :key="i.name">
        <a :href="i.href" :aria-current="activeName === i.name ? 'page' : undefined" @click="emit('navigate')">
          <Icon :name="i.icon" />
          <span>{{ i.label }}</span>
        </a>
      </li>
    </ul>
  </nav>
</template>

<style scoped>
ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
a { display: flex; align-items: center; gap: 12px; min-height: 44px; padding: 0 12px; border-radius: var(--r-sm); color: var(--text); text-decoration: none; font-weight: 600; }
a:hover { background: var(--surface-2); }
a[aria-current="page"] { background: var(--primary-soft); color: var(--primary); box-shadow: inset 3px 0 0 var(--primary); }
</style>
