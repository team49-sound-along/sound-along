<script setup>
import { computed, ref, watch } from "vue";
import Icon from "./components/Icon.vue";
import SideNav from "./components/SideNav.vue";
import RoleSwitcher from "./components/RoleSwitcher.vue";
import LibraryView from "./views/LibraryView.vue";
import ReaderView from "./views/ReaderView.vue";
import AssignmentsView from "./views/AssignmentsView.vue";
import GenerateView from "./views/GenerateView.vue";
import InsightsView from "./views/InsightsView.vue";
import SettingsView from "./views/SettingsView.vue";
import PronunciationsView from "./views/PronunciationsView.vue";
import ReviewView from "./views/ReviewView.vue";
import TeacherOnly from "./components/TeacherOnly.vue";
import { route, isTeacherOnly } from "./router.js";
import { role, USERS } from "./session.js";

const VIEWS = { library: LibraryView, read: ReaderView, assignments: AssignmentsView, generate: GenerateView, insights: InsightsView, settings: SettingsView, pronunciations: PronunciationsView, review: ReviewView };
const TITLES = { library: "Library", read: "Reader", assignments: "Assignments", generate: "Generate", insights: "Insights", settings: "Settings", pronunciations: "Pronunciations", review: "Pronunciation review" };
const view = computed(() => (isTeacherOnly(route.value.name) && role.value !== "teacher" ? TeacherOnly : VIEWS[route.value.name]));
const user = computed(() => USERS[role.value]);
const menuOpen = ref(false);
const main = ref(null);

watch(
  () => route.value.name + (route.value.params.id || ""),
  () => {
    menuOpen.value = false;
    document.title = `${TITLES[route.value.name]} | Sound Along`;
    window.scrollTo(0, 0);
    main.value?.focus({ preventScroll: true });
  },
  { immediate: true },
);
</script>

<template>
  <a class="skip" href="#main" @click.prevent="main?.focus()">Skip to main content</a>
  <div class="shell">
    <header class="topbar">
      <button class="btn menu-btn" type="button" :aria-expanded="menuOpen" aria-controls="side" @click="menuOpen = !menuOpen">
        <Icon :name="menuOpen ? 'close' : 'menu'" />
        <span class="sr-only">{{ menuOpen ? "Close menu" : "Open menu" }}</span>
      </button>
      <a class="brand" href="#/library" aria-label="Sound Along home">
        <span class="mark" aria-hidden="true"><span class="bar b1"></span><span class="bar b2"></span><span class="bar b3"></span></span>
        <span class="name">Sound Along</span>
      </a>
      <div class="spacer"></div>
      <RoleSwitcher />
      <div class="chip" :title="`Signed in as ${user.label}`">
        <span class="avatar" aria-hidden="true">{{ user.initials }}</span>
        <span class="who"><span class="sr-only">Signed in as </span>{{ user.label }}</span>
      </div>
    </header>
    <aside id="side" class="side" :class="{ open: menuOpen }">
      <SideNav @navigate="menuOpen = false" />
      <p class="small muted foot">Demo data. Sign-in is simulated.</p>
    </aside>
    <main id="main" ref="main" tabindex="-1">
      <component :is="view" :key="route.name + (route.params.id || '')" />
    </main>
  </div>
</template>

<style scoped>
.shell { display: grid; grid-template-columns: 240px minmax(0, 1fr); grid-template-rows: var(--topbar-h) 1fr; min-height: 100vh; }
.topbar { grid-column: 1 / -1; position: sticky; top: 0; z-index: 30; display: flex; align-items: center; gap: var(--s2); padding: 0 var(--s2); background: var(--surface); border-bottom: 1px solid var(--border); }
.spacer { flex: 1; }
.menu-btn { display: none; }
.brand { display: inline-flex; align-items: center; gap: 10px; color: var(--text); text-decoration: none; font-weight: 700; font-size: 18px; letter-spacing: -0.01em; min-height: 44px; }
.mark { display: inline-flex; align-items: flex-end; gap: 3px; height: 24px; padding: 4px; border-radius: 8px; background: var(--primary); }
.bar { width: 3px; border-radius: 2px; background: #fff; }
.b1 { height: 8px; } .b2 { height: 16px; background: var(--hl); } .b3 { height: 11px; }
.chip { display: inline-flex; align-items: center; gap: 8px; padding: 4px 12px 4px 4px; border: 1px solid var(--border); border-radius: 999px; min-height: 44px; font-size: 14px; font-weight: 600; }
.avatar { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: var(--primary-soft); color: var(--primary); font-size: 12px; font-weight: 700; }
.side { padding: var(--s2); border-right: 1px solid var(--border); background: var(--surface); display: flex; flex-direction: column; justify-content: space-between; position: sticky; top: var(--topbar-h); height: calc(100vh - var(--topbar-h)); }
main { min-width: 0; outline: none; }

@media (max-width: 860px) {
  .shell { grid-template-columns: minmax(0, 1fr); grid-template-rows: var(--topbar-h) 1fr; }
  .menu-btn { display: inline-flex; padding: 0; }
  .side { display: none; position: fixed; top: var(--topbar-h); left: 0; right: 0; z-index: 25; height: auto; border-right: 0; border-bottom: 1px solid var(--border); box-shadow: 0 12px 24px rgb(0 0 0 / 0.12); }
  .side.open { display: flex; }
}
@media (max-width: 380px) {
  /* 320px phones: the Teacher/Student switcher already shows the role, so the avatar chip makes way for it. */
  .chip { display: none; }
  .topbar { padding: 0 12px; }
}
@media (max-width: 640px) {
  .who { display: none; }
  .chip { padding: 4px; }
  .name { display: none; }
  .topbar { gap: 8px; }
}
</style>
