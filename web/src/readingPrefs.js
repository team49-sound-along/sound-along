// Reader preferences: text size, font, spacing, highlight style and two switches.
// Pure functions plus load/save helpers that take the storage object, so they are testable and never throw.

export const STORAGE_KEY = "soundalong.reading";

export const CHOICES = Object.freeze({
  size: ["large", "xl", "huge"],
  font: ["standard", "atkinson", "lexend"],
  spacing: ["normal", "roomy", "extra"],
  highlight: ["words", "sentences", "off"],
});

const SWITCHES = ["phraseBreaks", "reduceMotion"];

// Defaults follow the research notes: larger text for young readers, roomy spacing, word highlight, phrase breaks on.
export const DEFAULTS = Object.freeze({ size: "large", font: "standard", spacing: "roomy", highlight: "words", phraseBreaks: true, reduceMotion: false });

const SIZES = { large: "28px", xl: "34px", huge: "40px" };
const SPACING = {
  normal: { ls: "0.01em", ws: "0.04em", lh: "1.7" },
  roomy: { ls: "0.04em", ws: "0.14em", lh: "1.85" },
  extra: { ls: "0.07em", ws: "0.22em", lh: "2" },
};
const FONTS = {
  standard: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  atkinson: '"Atkinson Hyperlegible", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif',
  lexend: '"Lexend", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif',
};

/** Turn the page-wide calm mode on or off: while it is on, nothing in the app fades, slides or scrolls smoothly (see style.css, html.calm-page). */
export function applyMotionPreference(root, prefs) {
  if (!root?.classList) return;
  root.classList.toggle("calm-page", Boolean(sanitizePrefs(prefs).reduceMotion));
}

const isPlainObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);

/** Keep valid values, replace everything else with the default. Always returns a fresh object. */
export function sanitizePrefs(input) {
  const source = isPlainObject(input) ? input : {};
  const choices = Object.fromEntries(
    Object.entries(CHOICES).map(([key, allowed]) => [key, allowed.includes(source[key]) ? source[key] : DEFAULTS[key]]),
  );
  const switches = Object.fromEntries(SWITCHES.map((key) => [key, typeof source[key] === "boolean" ? source[key] : DEFAULTS[key]]));
  return { ...choices, ...switches };
}

/** CSS custom properties the reader applies to its passage. */
export function prefsToCssVars(prefs) {
  const clean = sanitizePrefs(prefs);
  const spacing = SPACING[clean.spacing];
  return {
    "--read-size": SIZES[clean.size],
    "--read-font": FONTS[clean.font],
    "--read-ls": spacing.ls,
    "--read-ws": spacing.ws,
    "--read-lh": spacing.lh,
  };
}

/** Return a new prefs object with one value changed. Unknown keys and invalid values change nothing. */
export function updatePref(prefs, key, value) {
  const clean = sanitizePrefs(prefs);
  const validChoice = CHOICES[key]?.includes(value);
  const validSwitch = SWITCHES.includes(key) && typeof value === "boolean";
  return validChoice || validSwitch ? { ...clean, [key]: value } : clean;
}

export function loadPrefs(storage) {
  try {
    const raw = storage?.getItem(STORAGE_KEY);
    return sanitizePrefs(raw ? JSON.parse(raw) : null);
  } catch {
    return sanitizePrefs(null); // blocked or corrupt storage: use defaults, the reader still works
  }
}

/** Returns true when saved, false when storage is missing or blocked. */
export function savePrefs(storage, prefs) {
  try {
    if (!storage) return false;
    storage.setItem(STORAGE_KEY, JSON.stringify(sanitizePrefs(prefs)));
    return true;
  } catch {
    return false;
  }
}
