import { readFile } from "node:fs/promises";
import path from "node:path";

/** Reads the stored job input <dataDir>/raw/<passageId>.json. Returns null when it is missing or unreadable JSON. */
export function createLocalSources({ dataDir }) {
  return {
    async read(passageId) {
      try {
        return JSON.parse(await readFile(path.join(dataDir, "raw", `${passageId}.json`), "utf8"));
      } catch (err) {
        if (err.code === "ENOENT" || err instanceof SyntaxError) return null;
        throw err;
      }
    },
  };
}
