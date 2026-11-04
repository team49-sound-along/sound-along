<script setup>
import { computed, ref, watch } from "vue";
import Icon from "./components/Icon.vue";
import TopNav from "./components/TopNav.vue";
import RoleSwitcher from "./components/RoleSwitcher.vue";
import LibraryView from "./views/LibraryView.vue";
import ReaderView from "./views/ReaderView.vue";
import AssignmentsView from "./views/AssignmentsView.vue";
import GenerateView from "./views/GenerateView.vue";
import InsightsView from "./views/InsightsView.vue";
import SettingsView from "./views/SettingsView.vue";
import PronunciationsView from "./views/PronunciationsView.vue";
import ReviewView from "./views/ReviewView.vue";
import ListeningView from "./views/ListeningView.vue";
import PracticeView from "./views/PracticeView.vue";
import TeacherOnly from "./components/TeacherOnly.vue";
import { route, isTeacherOnly } from "./router.js";
import { role, USERS } from "./session.js";

const VIEWS = { library: LibraryView, read: ReaderView, assignments: AssignmentsView, generate: GenerateView, insights: InsightsView, settings: SettingsView, pronunciations: PronunciationsView, review: ReviewView, listening: ListeningView, practice: PracticeView };
const TITLES = { library: "Library", read: "Reader", assignments: "Assignments", generate: "Generate", insights: "Insights", settings: "Settings", pronunciations: "Pronunciations", review: "Pronunciation review", listening: "Listening test" };
const view = computed(() => (isTeacherOnly(route.value.name) && role.value !== "teacher" ? TeacherOnly : VIEWS[route.value.name]));
const user = computed(() => USERS[role.value]);
// Reading mode: while a passage is open the page shows only the brand, a way back, and the passage.
const reading = computed(() => route.value.name === "read");
const menuOpen = ref(false);
const main = ref(null);
const menuButton = ref(null);

// Escape closes the phone menu and returns focus to its button.
function closeMenu() {
  if (!menuOpen.value) return;
  menuOpen.value = false;
  menuButton.value?.focus();
}

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
    <header class="topbar" @keydown.esc="closeMenu">
      <button v-if="!reading" ref="menuButton" class="btn menu-btn" type="button" :aria-expanded="menuOpen" aria-controls="main-nav" @click="menuOpen = !menuOpen">
        <Icon :name="menuOpen ? 'close' : 'menu'" />
        <span class="sr-only">{{ menuOpen ? "Close menu" : "Open menu" }}</span>
      </button>
      <a class="brand" href="#/library" aria-label="Sound Along home">
        <span class="mark" aria-hidden="true"><span class="bar b1"></span><span class="bar b2"></span><span class="bar b3"></span></span>
        <span class="name">Sound Along</span>
      </a>
      <TopNav v-if="!reading" id="main-nav" :open="menuOpen" @navigate="menuOpen = false" />
      <a v-else class="btn ghost back" href="#/library" aria-label="All passages"><Icon name="back" :size="18" /> <span class="back-label">All passages</span></a>
      <div class="spacer"></div>
      <RoleSwitcher />
      <div class="chip" :title="`Signed in as ${user.label}`">
        <span class="avatar" aria-hidden="true">{{ user.initials }}</span>
        <span class="who"><span class="sr-only">Signed in as </span>{{ user.label }}</span>
      </div>
    </header>
    <main id="main" ref="main" tabindex="-1">
      <h1 class="sr-only">Sound Along</h1>
      <component :is="view" :key="route.name + (route.params.id || '')" />
    </main>
    <footer class="demo small muted">Demo data. Sign-in is simulated.</footer>
  </div>
</template>

<style scoped>
.shell { display: grid; grid-template-rows: var(--topbar-h) 1fr auto; min-height: 100vh; }
.topbar { position: sticky; top: 0; z-index: 30; display: flex; align-items: center; gap: var(--s2); padding: 0 var(--s3); background: var(--surface); border-bottom: 1px solid var(--border); }
.spacer { flex: 1; }
.menu-btn { display: none; }
.brand { display: inline-flex; align-items: center; gap: 10px; color: var(--text); text-decoration: none; font-weight: 700; font-size: 18px; letter-spacing: -0.01em; min-height: 44px; margin-right: var(--s2); }
.mark { display: inline-flex; align-items: flex-end; gap: 3px; height: 24px; padding: 4px; border-radius: 8px; background: var(--primary); }
.bar { width: 3px; border-radius: 2px; background: #fff; }
.b1 { height: 8px; } .b2 { height: 16px; background: var(--hl); } .b3 { height: 11px; }
.name, .who { white-space: nowrap; }
.chip { display: inline-flex; align-items: center; gap: 8px; padding: 4px 12px 4px 4px; border: 1px solid var(--border); border-radius: 999px; min-height: 44px; font-size: 14px; font-weight: 600; }
.avatar { display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%; background: var(--primary-soft); color: var(--primary); font-size: 12px; font-weight: 700; }
main { min-width: 0; outline: none; }
.demo { padding: var(--s2) var(--s3); text-align: center; }

@media (max-width: 1000px) {
  .who { display: none; }
  .chip { padding: 4px; }
}
@media (max-width: 860px) {
  .menu-btn { display: inline-flex; padding: 0; }
  .topbar { padding: 0 var(--s2); gap: var(--s1); }
}
@media (max-width: 640px) {
  .who { display: none; }
  .chip { padding: 4px; }
  .name { display: none; }
}
@media (max-width: 480px) {
  .back-label { display: none; } /* phones: the arrow alone (the link keeps its "All passages" name) */
}
@media (max-width: 380px) {
  /* 320px phones: the Teacher/Student switcher already shows the role, so the avatar chip makes way for it. */
  .chip { display: none; }
  .topbar { padding: 0 8px; gap: 4px; }
}
</style>
