import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createApp } from "./src/app.js";
import { createFileCatalog } from "./src/catalog.js";
import { createJobStore } from "./src/jobs/jobStore.js";
import { createLocalRunner } from "./src/jobs/localRunner.js";
import { createLocalSources } from "./src/jobs/localSources.js";
import { createLocalRecordings } from "./src/recordings/localRecordings.js";
import { createFileManifest } from "./src/ratings/manifest.js";
import { createFileStore } from "./src/stores/fileStore.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const env = process.env;

const dataDir = path.resolve(env.DATA_DIR ?? path.join(root, "data"));
const config = {
  port: Number(env.PORT ?? 3101),
  host: env.HOST ?? "127.0.0.1",
  dataDir,
  webDist: existsSync(path.join(root, "web", "dist")) ? path.join(root, "web", "dist") : null,
  generationEnabled: (env.GENERATION_ENABLED ?? "true") === "true",
  generatePerMinute: Number(env.GENERATE_PER_MINUTE ?? 3),
  maxConcurrentJobs: Number(env.MAX_CONCURRENT_JOBS ?? 1),
  questionDraftsDir: path.resolve(env.QUESTION_DRAFTS_DIR ?? path.join(dataDir, "question-drafts")),
  trustProxy: false,
  readerInsights: (env.READER_INSIGHTS ?? "true") === "true", // on for local development and the demo scripts; off by default on AWS
};
const python = env.PYTHON ?? path.join(root, ".venv", "bin", "python");
const script = path.join(root, "services", "synth", "run_local.py");

const jobs = createJobStore();
const app = createApp({
  config,
  jobs,
  store: createFileStore(path.join(config.dataDir, "state.json")),
  catalog: createFileCatalog(config.dataDir),
  recordings: createLocalRecordings({ dataDir: config.dataDir }),
  sources: createLocalSources({ dataDir: config.dataDir }),
  manifest: createFileManifest(config.dataDir),
  runner: createLocalRunner({ jobs, dataDir: config.dataDir, python, script }),
});

app.listen(config.port, config.host, () => {
  process.stdout.write(`Sound Along API on http://${config.host}:${config.port} (data: ${config.dataDir}, ui: ${config.webDist ? "served" : "not built"})\n`);
});
