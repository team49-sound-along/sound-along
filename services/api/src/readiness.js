// Which passages are ready to read. A passage the generator marked `held` (its translation is still being made), a part of a long
// document whose other parts are not all there yet, and a translation whose original is not ready are all "pending": they are
// kept out of the Library until the whole document, with its translation, can be read. Absence of the marker means ready, so
// samples, passages without a translation and older data are never hidden.
const STALE_MS = 30 * 60 * 1000; // a document that stopped changing this long ago is shown as it is (a part failed or the generator was stopped)

/** Splits passage summaries into { ready, pending }. Pure: summaries are not changed. */
export function splitReady(passages, now = Date.now()) {
  const byId = new Map(passages.map((p) => [p.id, p]));
  const age = (p) => now - Date.parse(p.createdAt);
  const held = (p) => Boolean(p.held) && age(p) < STALE_MS;
  const memo = new Map();

  function ready(p, trail = new Set()) {
    if (memo.has(p.id)) return memo.get(p.id);
    if (trail.has(p.id)) return true;
    const next = new Set(trail).add(p.id);
    let ok = !held(p);
    if (ok && p.translationOf) {
      const original = byId.get(p.translationOf);
      ok = !original || ready(original, next);
    } else if (ok && p.series) {
      const parts = p.series.partIds.map((id) => byId.get(id));
      const recent = Math.min(...parts.filter(Boolean).map(age)) < STALE_MS; // some part was written lately: the document is still being made
      ok = !recent || parts.every((part) => part && !held(part));
    }
    memo.set(p.id, ok);
    return ok;
  }

  const out = { ready: [], pending: [] };
  for (const p of passages) (ready(p) ? out.ready : out.pending).push(p);
  return out;
}
