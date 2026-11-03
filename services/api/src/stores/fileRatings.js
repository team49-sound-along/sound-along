/** Blind-test ratings for the file store (state.json `ratings`). `load()` / `commit(update)` as in fileContent.js. */
export function createFileRatingMethods({ load, commit }) {
  return {
    async addRating(rating) {
      await commit((s) => ({ ...s, ratings: [...(s.ratings ?? []), { ...rating }] }));
    },
    async listRatings() {
      return [...((await load()).ratings ?? [])];
    },
  };
}
