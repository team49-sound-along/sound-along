// One plain word per reader, from how much of the passage they read across their reads. Never a rank or a grade. Pure; no DOM, no Vue.

const SHIFT = 8; // percentage points between the early and the recent reads before the label says anything changed
const LOW = 50; // reading under half of the passage, without improving, needs support
const mean = (list) => list.reduce((a, b) => a + b, 0) / list.length;

/** { label, tone }: "New", "Improving", "Steady" or "Support" (tone: new, up, steady, help). */
export function progressLabel(pcts) {
  if (!pcts || pcts.length < 2) return { label: "New", tone: "new" };
  const half = Math.floor(pcts.length / 2);
  const early = mean(pcts.slice(0, half));
  const recent = mean(pcts.slice(-half));
  if (recent >= early + SHIFT) return { label: "Improving", tone: "up" };
  if (recent <= early - SHIFT || recent < LOW) return { label: "Support", tone: "help" };
  return { label: "Steady", tone: "steady" };
}
