import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { resetReview } from "../src/questions/draft.js";

const DRAFT = /^([0-9a-f-]{36})\.draft\.json$/;
const inside = (child, parent) => {
  const rel = path.relative(parent, child);
  return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
};

/**
 * Local demo: copy question drafts into the folder the API reads them from, with every review field removed, so a person
 * starts with nothing approved. The source folder (samples/) is only read.
 */
export async function seedQuestionDrafts({ from, to, logger = console }) {
  const source = path.resolve(from);
  const target = path.resolve(to);
  if (inside(target, source) || inside(source, target)) throw new Error("Write the drafts to a different folder than the one they are read from.");
  let files;
  try {
    files = (await readdir(source)).filter((f) => DRAFT.test(f));
  } catch (err) {
    if (err.code === "ENOENT") throw new Error(`Drafts folder not found: ${source}`);
    throw err;
  }
  await mkdir(target, { recursive: true });
  const copied = [];
  for (const file of files) {
    let draft;
    try {
      draft = JSON.parse(await readFile(path.join(source, file), "utf8"));
    } catch {
      logger.warn(`skipping ${file}: not readable JSON`);
      continue;
    }
    await writeFile(path.join(target, file), `${JSON.stringify(resetReview(draft), null, 2)}\n`);
    copied.push(file.match(DRAFT)[1]);
  }
  logger.info(`Copied ${copied.length} draft(s) to ${target}, all unreviewed.`);
  return { copied };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
  const arg = (name, fallback) => {
    const i = process.argv.indexOf(`--${name}`);
    return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
  };
  const dataDir = path.resolve(process.env.DATA_DIR ?? path.join(root, "data"));
  seedQuestionDrafts({
    from: arg("from", path.join(root, "samples", "questions-v2")),
    to: arg("to", process.env.QUESTION_DRAFTS_DIR ?? path.join(dataDir, "question-drafts")),
    logger: { info: (m) => process.stdout.write(`${m}\n`), warn: (m) => process.stderr.write(`${m}\n`) },
  }).catch((err) => {
    process.stderr.write(`${err.message}\n`);
    process.exit(1);
  });
}
