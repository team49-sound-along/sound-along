import { randomUUID } from "node:crypto";
import { mkdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";

// Synthetic classes (no real student data). In AWS this list comes from DynamoDB.
export const CLASSES = Object.freeze([
  { id: "cls-g3-p2", name: "Period 2 Reading", grade: "Grade 3", students: 24 },
  { id: "cls-g4-p4", name: "Period 4 Reading", grade: "Grade 4", students: 27 },
  { id: "cls-g5-ell", name: "English Learner Support", grade: "Grade 5", students: 14 },
  { id: "cls-g4-int", name: "Reading Intervention Group B", grade: "Grade 4", students: 9 },
]);

const EMPTY = Object.freeze({ assignments: [], events: { plays: 0, wordTaps: 0, completions: 0 } });
export const EVENT_KEY = { play: "plays", word_tap: "wordTaps", complete: "completions" };

/**
 * JSON-file store behind a small interface (listClasses, assignments CRUD, recordEvent, counts).
 * Writes are serialised and atomic (temp file + rename). A DynamoDB store implements the same interface.
 */
export function createFileStore(filePath) {
  let state = null;
  let queue = Promise.resolve();

  async function load() {
    if (state) return state;
    try {
      state = { ...EMPTY, ...JSON.parse(await readFile(filePath, "utf8")) };
    } catch (err) {
      if (err.code !== "ENOENT") throw err;
      state = { ...EMPTY };
    }
    return state;
  }

  function commit(update) {
    const run = queue.then(async () => {
      const next = update(await load());
      await mkdir(path.dirname(filePath), { recursive: true });
      const tmp = `${filePath}.${process.pid}.tmp`;
      await writeFile(tmp, JSON.stringify(next, null, 1));
      await rename(tmp, filePath);
      state = next;
      return next;
    });
    queue = run.catch(() => undefined);
    return run;
  }

  return {
    async listClasses() {
      return CLASSES;
    },
    async listAssignments() {
      return [...(await load()).assignments].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
    },
    async createAssignment(input) {
      const assignment = { id: randomUUID(), ...input, createdAt: new Date().toISOString() };
      await commit((s) => ({ ...s, assignments: [...s.assignments, assignment] }));
      return assignment;
    },
    async updateAssignment(id, patch) {
      let updated = null;
      await commit((s) => ({
        ...s,
        assignments: s.assignments.map((a) => (a.id === id ? (updated = { ...a, ...patch }) : a)),
      }));
      return updated;
    },
    async deleteAssignment(id) {
      let removed = false;
      await commit((s) => {
        removed = s.assignments.some((a) => a.id === id);
        return { ...s, assignments: s.assignments.filter((a) => a.id !== id) };
      });
      return removed;
    },
    async recordEvent(type) {
      const key = EVENT_KEY[type];
      await commit((s) => ({ ...s, events: { ...s.events, [key]: s.events[key] + 1 } }));
    },
    async eventCounts() {
      return { ...(await load()).events };
    },
  };
}
