import { readdir, readFile, rm, stat } from "node:fs/promises";
import path from "node:path";
import { summarizePassage } from "./passageSummary.js";

const TIMING = /^([0-9a-f-]{36})\.timing\.json$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
/** The files the generator writes for one passage (pictures are content-hashed and may be shared, so they are kept). Same list as aws/s3PassageRemoval.js. */
export const PASSAGE_FILE_SUFFIXES = Object.freeze(["timing.json", "mp3", "soundalong.json", "cards.json", "questions.json", "pcm.npy"]);

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

  /** "generated" or "sample", from the `source` field inside raw/<id>.json (sample when there is no usable file). */
  async function sourceOf(id) {
    try {
      const raw = JSON.parse(await readFile(path.join(dataDir, "raw", `${id}.json`), "utf8"));
      return raw?.source === "generated" ? "generated" : "sample";
    } catch {
      return "sample";
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
        return { id: file.match(TIMING)[1], mtimeMs, timing, source: await sourceOf(file.match(TIMING)[1]) };
      }),
    );
    return loaded.sort((a, b) => b.mtimeMs - a.mtimeMs);
  }

  return {
    async list() {
      return (await all()).map(({ id, mtimeMs, timing, source }) => summarizePassage({ id, timing, mtimeMs, source }));
    },
    /** One passage's timing document (its words), or null when there is none. The server looks words up here; clients never send word text. */
    async timing(id) {
      if (!/^[0-9a-f-]{36}$/.test(String(id))) return null;
      try {
        return (await readTiming(`${id}.timing.json`)).timing;
      } catch (err) {
        if (err.code === "ENOENT") return null;
        throw err;
      }
    },
    /** Full timing documents, for metrics aggregation. */
    async timings() {
      return (await all()).map(({ timing }) => timing);
    },
    /** Passages carrying ASR review suspects, straight from the timing documents. */
    async reviewSources() {
      return (await all())
        .filter(({ timing }) => timing.review)
        .map(({ id, timing }) => ({ id, title: timing.title ?? "Untitled passage", review: timing.review }));
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
    /** Delete the passages' files and their stored job input. The timing file goes first, so a passage leaves the list even if a later file cannot be removed. */
    async remove(ids) {
      if (!ids.every((id) => UUID.test(id))) throw new Error("Invalid passage id.");
      for (const id of ids) {
        for (const suffix of PASSAGE_FILE_SUFFIXES) await rm(path.join(dataDir, `${id}.${suffix}`), { force: true });
        await rm(path.join(dataDir, "raw", `${id}.json`), { force: true });
        cache.delete(`${id}.timing.json`);
      }
    },
  };
}
