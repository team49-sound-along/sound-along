/**
 * Every passage linked to `id`: its voice pair (pairId) and its translations (translations / translationOf), in both directions, followed transitively.
 * The Library shows such a group as one card, so deleting the card removes the whole group and no "Also in ..." or voice link is left pointing nowhere.
 * Parts of a long document (series) are separate cards and are not followed. Returns the ids, `id` first, or [] when `id` is not listed.
 */
export function linkedPassageIds(passages, id) {
  const byId = new Map(passages.map((p) => [p.id, p]));
  if (!byId.has(id)) return [];
  const linksOf = (p) => [...Object.values(p.translations ?? {}), p.translationOf, p.pairId].filter(Boolean);
  const neighbours = new Map(passages.map((p) => [p.id, new Set()]));
  for (const p of passages) {
    for (const target of linksOf(p)) {
      if (!byId.has(target)) continue;
      neighbours.get(p.id).add(target);
      neighbours.get(target).add(p.id);
    }
  }
  const seen = new Set([id]);
  const queue = [id];
  while (queue.length) {
    for (const next of neighbours.get(queue.shift())) {
      if (!seen.has(next)) {
        seen.add(next);
        queue.push(next);
      }
    }
  }
  return [...seen];
}
