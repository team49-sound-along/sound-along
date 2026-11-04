import { mkdir, readdir, readFile, rename, writeFile } from "node:fs/promises";
import path from "node:path";
import { UUID } from "../recordings/rules.js";

const DRAFT_FILE = /^([0-9a-f-]{36})\.draft\.json$/;

/**
 * Question drafts and the served questions file on local disk.
 *   drafts   <draftsDir>/<id>.draft.json   (never served; the folder is not under the allow-listed /data route)
 *   served   <dataDir>/<id>.questions.json (written only by publish)
 * Same interface as the S3 version: listDraftIds(), readDraft(id), publish(id, doc).
 */
export function createLocalQuestions({ draftsDir, dataDir }) {
  return {
    async listDraftIds() {
      try {
        return (await readdir(draftsDir)).map((f) => f.match(DRAFT_FILE)?.[1]).filter((id) => id && UUID.test(id));
      } catch (err) {
        if (err.code === "ENOENT") return [];
        throw err;
      }
    },
    async readDraft(id) {
      if (!UUID.test(id)) return null;
      try {
        return JSON.parse(await readFile(path.join(draftsDir, `${id}.draft.json`), "utf8"));
      } catch (err) {
        if (err.code === "ENOENT" || err instanceof SyntaxError) return null;
        throw err;
      }
    },
    async publish(id, doc) {
      if (!UUID.test(id)) throw new Error("Invalid passage id.");
      await mkdir(dataDir, { recursive: true });
      const target = path.join(dataDir, `${id}.questions.json`);
      const temp = `${target}.${process.pid}.tmp`;
      await writeFile(temp, `${JSON.stringify(doc, null, 2)}\n`);
      await rename(temp, target); // readers see the old file or the new one, never half of one
    },
  };
}
