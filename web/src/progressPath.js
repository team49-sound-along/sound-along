// A reader's progress path: a row of dots, one per read, showing how much of the passage was read. Plain labels, never a rank or a grade.
// Pure; no DOM, no Vue.

const SHIFT = 8; // percentage points between the early and the recent reads before the label says anything changed
const LOW = 50; // reading under half of the passage, without improving, needs support
const mean = (list) => list.reduce((a, b) => a + b, 0) / list.length;

/** { label, tone } where tone is "new", "up", "steady" or "help" (the screen adds an icon to each, so colour is never the only signal). */
export function progressLabel(pcts) {
  if (!pcts || pcts.length < 2) return { label: "Just getting started", tone: "new" };
  const half = Math.floor(pcts.length / 2);
  const early = mean(pcts.slice(0, half));
  const recent = mean(pcts.slice(-half));
  if (recent >= early + SHIFT) return { label: "Reading more each time", tone: "up" };
  if (recent <= early - SHIFT || recent < LOW) return { label: "Needs support", tone: "help" };
  return { label: "Steady", tone: "steady" };
}

/** Dot positions inside a `width` x `height` box with `pad` on every side. A higher share sits higher. */
export function pathPoints(pcts, { width, height, pad }) {
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  return pcts.map((pct, k) => ({ x: pcts.length > 1 ? pad + (k * innerW) / (pcts.length - 1) : width / 2, y: pad + innerH - (pct / 100) * innerH, pct }));
}

export function pathSummary(pcts) {
  if (!pcts?.length) return "No reads yet";
  const n = pcts.length;
  return n === 1 ? `Read ${pcts[0]}% of the passage in 1 read` : `Read ${pcts.join("%, ")}% of the passage over ${n} reads`;
}
