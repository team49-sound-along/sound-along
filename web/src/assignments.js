// Pure, immutable helpers for assignment lists.

/** Teachers always get audio. A student gets text-only only when every assignment for the passage has Sound Along off. */
export function soundAlongAllowed(assignments, passageId, role) {
  if (role !== "student") return true;
  const mine = assignments.filter((a) => a.passageId === passageId);
  return mine.length === 0 || mine.some((a) => a.soundAlong);
}

export const replaceAssignment = (list, updated) => list.map((a) => (a.id === updated.id ? updated : a));
export const removeAssignment = (list, id) => list.filter((a) => a.id !== id);
export const prependAssignment = (list, created) => [created, ...list];

export function filterPassages(passages, query) {
  const q = String(query || "").trim().toLowerCase();
  return q ? passages.filter((p) => p.title.toLowerCase().includes(q)) : passages;
}
