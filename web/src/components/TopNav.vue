<script setup>
// Main navigation in the top bar. Library, Assignments and Insights are always visible; the rest sit under "More".
// On a phone the whole list opens as one panel from the menu button in App.vue.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { route } from "../router.js";
import { role } from "../session.js";

defineProps({ open: Boolean });
const emit = defineEmits(["navigate"]);
const moreOpen = ref(false);
const root = ref(null);
const moreButton = ref(null);

// The "More" menu closes on Escape (focus returns to its button), when focus leaves it, and on a click outside.
function closeMore(returnFocus = false) {
  moreOpen.value = false;
  if (returnFocus) moreButton.value?.focus();
}
const onFocusOut = (event) => {
  if (moreOpen.value && !root.value?.contains(event.relatedTarget)) moreOpen.value = false;
};
const onDocumentPointer = (event) => {
  if (moreOpen.value && root.value && !root.value.contains(event.target)) moreOpen.value = false;
};
onMounted(() => document.addEventListener("pointerdown", onDocumentPointer));
onBeforeUnmount(() => document.removeEventListener("pointerdown", onDocumentPointer));

const primary = computed(() => [
  { name: "library", href: "#/library", label: "Library" },
  { name: "assignments", href: "#/assignments", label: role.value === "student" ? "My assignments" : "Assignments" },
  { name: "insights", href: "#/insights", label: "Insights" },
]);
const more = computed(() => [
  { name: "generate", href: "#/generate", label: "Generate" },
  { name: "listening", href: "#/listening", label: "Listening test" },
  ...(role.value === "teacher"
    ? [
        { name: "settings", href: "#/settings", label: "Settings" },
        { name: "pronunciations", href: "#/pronunciations", label: "Pronunciations" },
        { name: "review", href: "#/review", label: "Pronunciation review" },
      ]
    : []),
]);
const activeName = computed(() => (route.value.name === "read" ? "library" : route.value.name));
const moreActive = computed(() => more.value.some((i) => i.name === activeName.value));

function go() {
  moreOpen.value = false;
  emit("navigate");
}
</script>

<template>
  <nav ref="root" aria-label="Main" class="nav" :class="{ open }" @keydown.esc="closeMore(true)" @focusout="onFocusOut">
    <ul class="primary">
      <li v-for="i in primary" :key="i.name">
        <a :href="i.href" :aria-current="activeName === i.name ? 'page' : undefined" @click="go">{{ i.label }}</a>
      </li>
    </ul>
    <div class="more">
      <button ref="moreButton" class="morebtn" type="button" :class="{ active: moreActive }" :aria-expanded="moreOpen" aria-controls="more-menu" @click="moreOpen = !moreOpen">More</button>
      <ul v-show="moreOpen" id="more-menu" class="menu">
        <li v-for="i in more" :key="i.name">
          <a :href="i.href" :aria-current="activeName === i.name ? 'page' : undefined" @click="go">{{ i.label }}</a>
        </li>
      </ul>
    </div>
  </nav>
</template>

<style scoped>
.nav { display: flex; align-items: center; gap: var(--s1); }
ul { list-style: none; margin: 0; padding: 0; }
.primary { display: flex; gap: var(--s1); }
a, .morebtn { display: inline-flex; align-items: center; min-height: 44px; padding: 0 14px; border: 0; border-radius: var(--r-sm); background: transparent; color: var(--muted); font-weight: 600; font-size: 15px; text-decoration: none; cursor: pointer; }
a:hover, .morebtn:hover { color: var(--text); background: var(--surface-2); }
a[aria-current="page"], .morebtn.active { color: var(--primary); box-shadow: inset 0 -3px 0 var(--primary); border-radius: 0; }
.more { position: relative; }
.menu { position: absolute; right: 0; top: calc(100% + 4px); min-width: 220px; display: grid; gap: 2px; padding: 6px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); box-shadow: 0 12px 28px rgb(31 42 48 / 0.14); z-index: 40; }
.menu a { width: 100%; }

@media (max-width: 860px) {
  .nav { display: none; position: fixed; top: var(--topbar-h); left: 0; right: 0; z-index: 25; flex-direction: column; align-items: stretch; padding: var(--s1) var(--s2) var(--s2); background: var(--surface); border-bottom: 1px solid var(--border); box-shadow: 0 12px 24px rgb(31 42 48 / 0.12); }
  .nav.open { display: flex; }
  .primary { flex-direction: column; }
  .morebtn { display: none; }
  .menu { display: grid !important; position: static; min-width: 0; padding: 0; border: 0; box-shadow: none; }
  a[aria-current="page"] { box-shadow: inset 3px 0 0 var(--primary); background: var(--primary-soft); }
}
</style>
