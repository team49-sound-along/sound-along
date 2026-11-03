/**
 * Settings, pronunciation fixes and dismissed review words for the file store.
 * `load()` returns the current state and `commit(update)` applies a pure state -> state function.
 */
export function createFileContentMethods({ load, commit }) {
  return {
    async getSettings() {
      return (await load()).settings ?? null;
    },
    async putSettings(settings) {
      await commit((s) => ({ ...s, settings: { ...settings } }));
      return { ...settings };
    },
    async listPronunciations() {
      const stored = (await load()).pronunciations ?? {};
      return Object.entries(stored)
        .map(([word, value]) => ({ word, ...value }))
        .sort((a, b) => a.word.localeCompare(b.word));
    },
    async putPronunciation(word, respelling) {
      const pronunciation = { word, respelling, updatedAt: new Date().toISOString() };
      let created = true;
      await commit((s) => {
        created = !(word in (s.pronunciations ?? {}));
        return { ...s, pronunciations: { ...s.pronunciations, [word]: { respelling, updatedAt: pronunciation.updatedAt } } };
      });
      return { pronunciation, created };
    },
    async deletePronunciation(word) {
      let removed = false;
      await commit((s) => {
        const { [word]: gone, ...rest } = s.pronunciations ?? {};
        removed = gone !== undefined;
        return { ...s, pronunciations: rest };
      });
      return removed;
    },
    async listDismissed() {
      return [...((await load()).dismissed ?? [])];
    },
    async addDismissed(word) {
      await commit((s) => ({ ...s, dismissed: [...new Set([...(s.dismissed ?? []), word])] }));
    },
  };
}
