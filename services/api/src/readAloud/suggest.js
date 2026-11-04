// Plain, kind next steps for a teacher, from the aggregated numbers. Pure; wording is about the class, never a child.
const MAX_WORD_STEPS = 3;

export function suggestSteps({ totals, words }) {
  const steps = [];
  const trouble = words.filter((w) => w.missed >= 2 && w.share >= 0.25).slice(0, MAX_WORD_STEPS);
  for (const w of trouble) {
    steps.push(
      w.skipped >= w.differs
        ? `Add "${w.word}" to this class's word practice.`
        : `Say "${w.word}" aloud together before reading: it is often heard as a different word.`,
    );
  }
  if (totals.finishRate !== null && totals.finishRate < 0.5) steps.push("Fewer than half of the sessions reached the end. Try reading the first paragraph together, or choose a shorter passage.");
  if (totals.retryRate !== null && totals.retryRate >= 0.5) steps.push("Many students tried again. Pause on a hard sentence and read it together once.");
  if (steps.length === 0 && totals.sessions > 0) steps.push("No word stands out. Keep this passage as it is.");
  return steps;
}
