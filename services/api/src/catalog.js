import { access, readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { summarizePassage } from "./passageSummary.js";

const TIMING = /^([0-9a-f-]{36})\.timing\.json$/;

/**
 * Passage catalog over a data directory of generated artifacts (<id>.timing.json + <id>.mp3).
 * In AWS the same interface reads S3 (ListObjectsV2 + GetObject).
 */
export function createFileCatalog(dataDir) {
  const cache = new Map(); // file -> { mtimeMs, timing }

  async function readTiming(file) {
    const full = path.join(dataDir, file);
    const { mtimeMs } = await stat(full);
    const hit = cache.get(file);
    if (hit?.mtimeMs === mtimeMs) return { mtimeMs, timing: hit.timing };
    const timing = JSON.parse(await readFile(full, "utf8"));
    cache.set(file, { mtimeMs, timing });
    return { mtimeMs, timing };
  }

  async function isGenerated(id) {
    try {
      await access(path.join(dataDir, "raw", `${id}.json`));
      return true;
    } catch {
      return false;
    }
  }

  async function all() {
    let files = [];
    try {
      files = (await readdir(dataDir)).filter((f) => TIMING.test(f));
    } catch (err) {
      if (err.code !== "ENOENT") throw err;
    }
    const loaded = await Promise.all(
      files.map(async (file) => {
        const { mtimeMs, timing } = await readTiming(file);
        return { id: file.match(TIMING)[1], mtimeMs, timing, generated: await isGenerated(file.match(TIMING)[1]) };
      }),
    );
    return loaded.sort((a, b) => b.mtimeMs - a.mtimeMs);
  }

  return {
    async list() {
      return (await all()).map(({ id, mtimeMs, timing, generated }) => summarizePassage({ id, timing, mtimeMs, generated }));
    },
    /** Full timing documents, for metrics aggregation. */
    async timings() {
      return (await all()).map(({ timing }) => timing);
    },
    /** Measured quality report written by scripts/build_samples.py, or null if it has not been run. */
    async qualityReport() {
      try {
        return JSON.parse(await readFile(path.join(dataDir, "quality-report.json"), "utf8"));
      } catch (err) {
        if (err.code === "ENOENT") return null;
        throw err;
      }
    },
  };
}
