// A long document is generated as a series of linked parts (see docs/DEPLOY.md, "Long documents"). Helpers for the Library and the Reader.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** {id, index, total, title, partIds} for a part of a document; null when the data is missing or malformed (the passage is then an ordinary one). */
export function seriesInfo(source) {
  const s = source?.series ?? null;
  const ids = s?.partIds;
  if (!Array.isArray(ids) || ids.length < 2 || ids.length > 40 || !ids.every((i) => typeof i === "string" && UUID.test(i))) return null;
  if (typeof s.id !== "string" || !UUID.test(s.id) || s.total !== ids.length || !Number.isInteger(s.index) || s.index < 1 || s.index > s.total) return null;
  return { id: s.id, index: s.index, total: s.total, title: typeof s.title === "string" ? s.title : "", partIds: ids };
}

/**
 * The previous (delta -1) or next (+1) part of the document this timing belongs to.
 * { state: "ready", id } when it can be opened, { state: "pending" } when it has not been created yet, null when there is no such part.
 * A translated part leads to the translation of its neighbour, found through the neighbour's own link, so the language stays the same.
 */
export async function neighborPart(timing, delta, fetchTiming) {
  const s = seriesInfo(timing);
  if (!s) return null;
  const at = s.index - 1 + delta;
  if (at < 0 || at >= s.total) return null;
  const neighborId = s.partIds[at];
  let neighbor;
  try {
    neighbor = await fetchTiming(neighborId);
  } catch {
    return { state: "pending" };
  }
  if (timing.translationOf) {
    const translated = neighbor?.translations?.[timing.language]?.id;
    return translated ? { state: "ready", id: translated } : { state: "pending" };
  }
  return { state: "ready", id: neighborId };
}

/**
 * One Library entry per document: the parts of a series are replaced by a single entry, placed where its first part was.
 * The entry has `isSeries`, `parts` (the parts that exist, in order), `total` (how many there will be) and the title of the whole document.
 */
export function groupSeries(passages) {
  const parts = new Map();
  for (const p of passages) {
    const s = seriesInfo(p);
    if (s) parts.set(s.id, [...(parts.get(s.id) ?? []), p]);
  }
  const done = new Set();
  const out = [];
  for (const p of passages) {
    const s = seriesInfo(p);
    if (!s) {
      out.push(p);
      continue;
    }
    if (done.has(s.id)) continue;
    done.add(s.id);
    const ordered = [...parts.get(s.id)].sort((a, b) => seriesInfo(a).index - seriesInfo(b).index);
    const first = ordered[0];
    const langs = [...new Set(ordered.flatMap((x) => x.translationLangs ?? []))].filter((l) => ordered.every((x) => (x.translationLangs ?? []).includes(l)));
    out.push({
      ...first,
      id: `series:${s.id}`,
      title: s.title || first.title,
      isSeries: true,
      parts: ordered,
      total: s.total,
      words: ordered.reduce((n, x) => n + (x.words ?? 0), 0),
      durationMs: ordered.reduce((n, x) => n + (x.durationMs ?? 0), 0),
      ...(langs.length ? { translationLangs: langs } : { translationLangs: undefined }),
    });
  }
  return out;
}
