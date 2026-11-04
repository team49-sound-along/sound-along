import { createApp } from "vue";
import App from "./App.vue";
import "./style.css";
import "./fonts.css"; // self-hosted reading fonts, see src/assets/fonts/README.md
import { applyMotionPreference, loadPrefs } from "./readingPrefs.js";

try {
  applyMotionPreference(document.documentElement, loadPrefs(window.localStorage)); // the saved "Reduce motion" choice applies from the first screen
} catch {
  /* storage unavailable: the default (motion on) stays */
}

createApp(App).mount("#app");
