// Passage language helpers (docs/API.md v3). English is the default everywhere.
export const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "es", label: "Spanish" },
];

export const isSpanish = (passage) => passage?.language === "es";

/** Value for the HTML lang attribute: only "es" is recognised, anything else is English. */
export const langAttr = (language) => (language === "es" ? "es" : "en");

/** Voices of one language. Entries without `lang` are treated as English (older servers). */
export const voicesFor = (voices, lang) => (Array.isArray(voices) ? voices : []).filter((v) => (v.lang ?? "en") === lang);

const COPY = {
  en: {
    textLabel: "Passage text",
    titlePlaceholder: "",
    textPlaceholder: "",
    help: "",
  },
  es: {
    textLabel: "Texto del pasaje",
    titlePlaceholder: "Título del pasaje",
    textPlaceholder: "Pega o escribe aquí el texto en español.",
    help: "Escribe el texto con sus acentos y signos (á, é, ñ, ¿, ¡). Spanish word timing can be a little less exact than English.",
  },
};

export const languageCopy = (language) => COPY[langAttr(language)];

export const PRONUNCIATION_NOTE = "Pronunciation fixes apply to English passages only.";

/** Body for POST /api/generate. */
export const withLanguage = (body, language) => ({ ...body, language: langAttr(language) });
